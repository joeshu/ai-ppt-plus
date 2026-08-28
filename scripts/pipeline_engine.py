#!/usr/bin/env python3
"""Small dependency-aware executor used by the verification pipeline.

The engine deliberately has no project-specific knowledge.  A task declares
its command, dependencies, input paths and output paths.  Successful tasks
may be copied into a content-addressed cache and restored into a fresh run
directory.  Failed tasks are never cached.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Iterable


CACHE_SCHEMA = "ai-ppt-plus/pipeline-cache/v1"
ENGINE_VERSION = "pipeline-engine-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_digest(path: Path) -> dict[str, Any]:
    if path.is_file():
        return {"path": path.name, "kind": "file", "sha256": sha256(path), "size": path.stat().st_size}
    if not path.is_dir():
        return {"path": path.name, "kind": "missing"}
    files = []
    for child in sorted((item for item in path.rglob("*") if item.is_file()), key=lambda item: str(item.relative_to(path))):
        files.append({
            "path": str(child.relative_to(path)),
            "sha256": sha256(child),
            "size": child.stat().st_size,
        })
    return {"path": path.name, "kind": "directory", "files": files}


def _json_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_relative(value: Any) -> Path | None:
    """Accept only non-empty relative cache artifact paths."""
    if not isinstance(value, str) or not value.strip():
        return None
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        return None
    return relative


@dataclass
class PipelineTask:
    """One executable node in the pipeline graph."""

    name: str
    args: list[str] = field(default_factory=list)
    deps: tuple[str, ...] = ()
    outputs: tuple[Path, ...] = ()
    inputs: tuple[Path, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    timeout: int = 600
    cacheable: bool = True
    static_result: dict[str, Any] | None = None


class PipelineExecutor:
    """Execute tasks in insertion-stable topological order.

    ``mode=linear`` uses one worker and disables the cache.  ``mode=dag``
    runs ready independent tasks concurrently and enables the declared cache.
    """

    def __init__(
        self,
        run_dir: Path,
        *,
        mode: str = "dag",
        cache_dir: Path | None = None,
        max_workers: int = 4,
    ) -> None:
        if mode not in {"dag", "linear"}:
            raise ValueError(f"unsupported execution mode: {mode}")
        self.run_dir = Path(run_dir).resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.mode = mode
        self.cache_dir = Path(cache_dir).resolve() if cache_dir else None
        self.max_workers = max(1, int(max_workers)) if mode == "dag" else 1
        self.tasks: list[PipelineTask] = []
        self._task_names: set[str] = set()

    def add(self, task: PipelineTask) -> PipelineTask:
        if task.name in self._task_names:
            raise ValueError(f"duplicate pipeline task: {task.name}")
        if any(dep == task.name for dep in task.deps):
            raise ValueError(f"task cannot depend on itself: {task.name}")
        self.tasks.append(task)
        self._task_names.add(task.name)
        return task

    def _normalize_arg(self, value: str) -> str:
        try:
            path = Path(value).resolve()
            relative = path.relative_to(self.run_dir)
            return "<run_dir>/" + str(relative)
        except (OSError, ValueError):
            return value

    def _cache_key(self, task: PipelineTask) -> tuple[str, dict[str, Any]]:
        script_hash = None
        if task.args:
            candidate = Path(task.args[0])
            if candidate.is_file():
                script_hash = sha256(candidate)
        inputs = []
        for path in sorted((Path(item).resolve() for item in task.inputs), key=str):
            record = _tree_digest(path)
            try:
                record["path"] = str(path.relative_to(self.run_dir))
            except ValueError:
                record["path"] = str(path)
            inputs.append(record)
        payload = {
            "schema": CACHE_SCHEMA,
            "engine_version": ENGINE_VERSION,
            "task": task.name,
            "command": [self._normalize_arg(str(value)) for value in task.args],
            "script_sha256": script_hash,
            "inputs": inputs,
            "metadata": task.metadata,
        }
        return _json_hash(payload), payload

    def _output_record(self, path: Path) -> dict[str, Any] | None:
        path = Path(path).resolve()
        if not path.exists():
            return None
        try:
            relative = path.relative_to(self.run_dir)
        except ValueError:
            return None
        if not relative.parts:
            return None
        return {"relative": str(relative), "kind": "directory" if path.is_dir() else "file"}

    def _cache_entry(self, key: str) -> Path:
        if not self.cache_dir:
            raise RuntimeError("cache directory is not configured")
        return self.cache_dir / key

    def _restore_cache(self, task: PipelineTask, key: str) -> dict[str, Any] | None:
        if self.mode != "dag" or not task.cacheable or not self.cache_dir:
            return None
        entry = self._cache_entry(key)
        metadata_path = entry / "metadata.json"
        if not metadata_path.is_file():
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if metadata.get("schema") != CACHE_SCHEMA or metadata.get("cache_key") != key or metadata.get("ok") is not True:
            return None
        artifacts = metadata.get("artifacts", [])
        if not isinstance(artifacts, list):
            return None
        safe_artifacts = []
        for artifact in artifacts:
            if not isinstance(artifact, dict) or not artifact.get("relative"):
                return None
            relative = _safe_relative(artifact["relative"])
            if relative is None or artifact.get("kind") not in {"file", "directory"}:
                return None
            source = entry / "artifacts" / relative
            if artifact["kind"] == "directory" and not source.is_dir():
                return None
            if artifact["kind"] == "file" and not source.is_file():
                return None
            safe_artifacts.append((relative, artifact["kind"], source))
        try:
            for relative, kind, source in safe_artifacts:
                target = self.run_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                if kind == "directory":
                    shutil.copytree(source, target)
                else:
                    shutil.copy2(source, target)
        except (OSError, shutil.Error):
            return None
        started = time.perf_counter()
        stdout_path = self.run_dir / f"{task.name}.stdout.txt"
        stderr_path = self.run_dir / f"{task.name}.stderr.txt"
        stdout_path.write_text(f"cache hit: {key}\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        result = dict(metadata.get("result") or {})
        result.update({
            "name": task.name,
            "command": [sys.executable, *task.args],
            "stdout": str(stdout_path.resolve()),
            "stderr": str(stderr_path.resolve()),
            "timeout_seconds": task.timeout,
            "cache_key": key,
            "cache_hit": True,
            "deps": list(task.deps),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        })
        return result

    def _save_cache(self, task: PipelineTask, key: str, result: dict[str, Any]) -> None:
        if self.mode != "dag" or not task.cacheable or not self.cache_dir or not result.get("ok"):
            return
        artifacts = []
        for output in task.outputs:
            record = self._output_record(Path(output))
            if record:
                artifacts.append(record)
        entry = self._cache_entry(key)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_dir / f".{key}.tmp-{os.getpid()}-{time.time_ns()}"
        try:
            (temporary / "artifacts").mkdir(parents=True)
            for artifact in artifacts:
                source = self.run_dir / artifact["relative"]
                target = temporary / "artifacts" / artifact["relative"]
                target.parent.mkdir(parents=True, exist_ok=True)
                if artifact["kind"] == "directory":
                    shutil.copytree(source, target)
                else:
                    shutil.copy2(source, target)
            cache_result = {key: value for key, value in result.items() if key not in {"stdout", "stderr", "duration_ms", "cache_hit"}}
            metadata = {
                "schema": CACHE_SCHEMA,
                "cache_key": key,
                "task": task.name,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "ok": True,
                "artifacts": artifacts,
                "result": cache_result,
            }
            (temporary / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            if entry.exists():
                shutil.rmtree(temporary)
            else:
                os.replace(temporary, entry)
        except OSError:
            shutil.rmtree(temporary, ignore_errors=True)

    def _run_task(self, task: PipelineTask) -> dict[str, Any]:
        key, _payload = self._cache_key(task)
        cached = self._restore_cache(task, key)
        if cached is not None:
            return cached
        started = time.perf_counter()
        stdout_path = self.run_dir / f"{task.name}.stdout.txt"
        stderr_path = self.run_dir / f"{task.name}.stderr.txt"
        if task.static_result is not None:
            result = dict(task.static_result)
            result.setdefault("name", task.name)
            result.setdefault("command", [])
            result.setdefault("stdout", "")
            result.setdefault("stderr", "")
            result.setdefault("exit_code", 0 if result.get("ok") else 2)
            result.setdefault("ok", result.get("exit_code") == 0)
            result.setdefault("timeout_seconds", task.timeout)
        else:
            command = [sys.executable, *task.args]
            try:
                completed = subprocess.run(command, capture_output=True, text=True, timeout=task.timeout, check=False)
                stdout = completed.stdout
                stderr = completed.stderr
                exit_code = completed.returncode
                failure = None
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout or ""
                stderr = (exc.stderr or "") + f"\nstep timed out after {task.timeout}s"
                exit_code = 124
                failure = "timeout"
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr, encoding="utf-8")
            result = {
                "name": task.name,
                "command": command,
                "exit_code": exit_code,
                "ok": exit_code == 0,
                "stdout": str(stdout_path.resolve()),
                "stderr": str(stderr_path.resolve()),
                "timeout_seconds": task.timeout,
            }
            if failure:
                result["failure"] = failure
        result.update({
            "cache_key": key,
            "cache_hit": False,
            "deps": list(task.deps),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        })
        self._save_cache(task, key, result)
        return result

    def _blocked_result(self, task: PipelineTask, failed_deps: Iterable[str]) -> dict[str, Any]:
        stdout_path = self.run_dir / f"{task.name}.stdout.txt"
        stderr_path = self.run_dir / f"{task.name}.stderr.txt"
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("dependency failed; task was not executed\n", encoding="utf-8")
        key, _payload = self._cache_key(task)
        return {
            "name": task.name,
            "command": [sys.executable, *task.args],
            "exit_code": 125,
            "ok": False,
            "stdout": str(stdout_path.resolve()),
            "stderr": str(stderr_path.resolve()),
            "timeout_seconds": task.timeout,
            "failure": "dependency_failed",
            "blocked_by": sorted(failed_deps),
            "cache_key": key,
            "cache_hit": False,
            "deps": list(task.deps),
            "duration_ms": 0.0,
        }

    def run(self) -> list[dict[str, Any]]:
        by_name = {task.name: task for task in self.tasks}
        missing_deps = {
            task.name: [dep for dep in task.deps if dep not in by_name]
            for task in self.tasks
        }
        results: dict[str, dict[str, Any]] = {}
        pending = set(by_name)
        while pending:
            progressed = False
            for name in list(pending):
                if missing_deps[name]:
                    results[name] = self._blocked_result(by_name[name], missing_deps[name])
                    pending.remove(name)
                    progressed = True
            ready = [
                by_name[name]
                for name in pending
                if all(dep in results for dep in by_name[name].deps)
            ]
            if ready:
                if self.max_workers == 1 or len(ready) == 1:
                    for task in sorted(ready, key=lambda item: self.tasks.index(item)):
                        failed = [dep for dep in task.deps if not results[dep].get("ok")]
                        results[task.name] = self._blocked_result(task, failed) if failed else self._run_task(task)
                        pending.remove(task.name)
                else:
                    with ThreadPoolExecutor(max_workers=min(self.max_workers, len(ready)), thread_name_prefix="ppt-pipeline") as pool:
                        futures = {}
                        for task in ready:
                            failed = [dep for dep in task.deps if not results[dep].get("ok")]
                            if failed:
                                results[task.name] = self._blocked_result(task, failed)
                                pending.remove(task.name)
                            else:
                                futures[pool.submit(self._run_task, task)] = task
                        for future in as_completed(futures):
                            task = futures[future]
                            try:
                                results[task.name] = future.result()
                            except Exception as exc:  # executor failure is a hard pipeline failure
                                results[task.name] = self._blocked_result(task, [f"executor:{type(exc).__name__}"])
                            pending.remove(task.name)
                progressed = True
            if not progressed:
                cycle = sorted(pending)
                for name in cycle:
                    results[name] = self._blocked_result(by_name[name], ["dependency_cycle"])
                break
        return [results[task.name] for task in self.tasks]


def input_paths_from_args(args: Iterable[str], *, exclude: Iterable[Path] = ()) -> tuple[Path, ...]:
    """Best-effort input discovery for small callers and tests.

    Explicit ``PipelineTask.inputs`` remains preferred.  This helper only
    returns existing file/directory arguments and ignores option values that
    are clearly outputs.
    """
    excluded = {Path(item).resolve() for item in exclude}
    found = []
    for value in args:
        candidate = Path(value)
        if not candidate.exists():
            continue
        resolved = candidate.resolve()
        if resolved in excluded or resolved.name.endswith((".stdout.txt", ".stderr.txt")):
            continue
        found.append(resolved)
    return tuple(dict.fromkeys(found))
