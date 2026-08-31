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
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Iterable

from atomic_output import atomic_write_json, atomic_write_text


CACHE_SCHEMA = "ai-ppt-plus/pipeline-cache/v3"
ENGINE_VERSION = "pipeline-engine-v2"
CACHE_EXCLUDED_DIRS = {".git", ".pipeline-cache", "pipeline-runs", "__pycache__"}
RUNTIME_PACKAGES = ("numpy", "Pillow", "python-pptx", "PyYAML", "cairosvg")
RUNTIME_BINARIES = ("soffice", "libreoffice", "pdftoppm", "pdftocairo", "inkscape", "fc-match")
CACHE_LOCK_TIMEOUT_SECONDS = 30.0
CACHE_LOCK_STALE_SECONDS = 900.0


def as_text(value: Any) -> str:
    """Normalize subprocess output from both text and timeout paths."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


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
        relative = child.relative_to(path)
        if any(part in CACHE_EXCLUDED_DIRS for part in relative.parts[:-1]):
            continue
        files.append({
            "path": str(relative),
            "sha256": sha256(child),
            "size": child.stat().st_size,
        })
    return {"path": path.name, "kind": "directory", "files": files}


def _json_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _artifact_digest(path: Path) -> str:
    """Return a content digest for a file or an excluded-tree-aware directory."""
    path = Path(path)
    if path.is_file():
        return sha256(path)
    return _json_hash(_tree_digest(path))


def _local_code_fingerprint() -> str:
    """Hash all local pipeline modules so imported helper changes invalidate cache."""
    records = []
    for path in sorted(Path(__file__).resolve().parent.glob("*.py"), key=str):
        records.append({"path": path.name, "sha256": sha256(path), "size": path.stat().st_size})
    return _json_hash(records)


def _runtime_fingerprint() -> dict[str, Any]:
    """Capture versions that can change PPTX reports or rendered pixels."""
    packages = {}
    for package in RUNTIME_PACKAGES:
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    binaries = {}
    for name in RUNTIME_BINARIES:
        binary = shutil.which(name)
        if not binary:
            binaries[name] = None
            continue
        try:
            completed = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=5, check=False)
            output = (completed.stdout or completed.stderr).strip().splitlines()
            binaries[name] = output[0] if output else f"exit:{completed.returncode}"
        except (OSError, subprocess.TimeoutExpired) as exc:
            binaries[name] = f"unavailable:{type(exc).__name__}"
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": packages,
        "binaries": binaries,
    }


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
        self.code_fingerprint = _local_code_fingerprint()
        self.runtime_fingerprint = _runtime_fingerprint()
        self.last_wall_duration_ms = 0.0
        self.last_cache_hits = 0
        self.last_cache_misses = 0
        self.last_critical_path_ms = 0.0

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
            "local_code_fingerprint": self.code_fingerprint,
            "runtime": self.runtime_fingerprint,
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
        return {
            "relative": str(relative),
            "kind": "directory" if path.is_dir() else "file",
            "sha256": _artifact_digest(path),
            "size": path.stat().st_size if path.is_file() else None,
        }

    def _cache_entry(self, key: str) -> Path:
        if not self.cache_dir:
            raise RuntimeError("cache directory is not configured")
        return self.cache_dir / key

    def _cache_lock(self, key: str) -> Path:
        if not self.cache_dir:
            raise RuntimeError("cache directory is not configured")
        return self.cache_dir / f".{key}.lock"

    def _acquire_cache_lock(self, key: str) -> Path | None:
        """Acquire a cross-process lock for one cache key.

        Cache entries are immutable once published.  The lock only protects
        the temporary-copy/publish window so two workers cannot race to
        publish or remove the same entry.  A stale lock is recoverable and
        is removed only when its recorded age exceeds the safety threshold.
        """
        if not self.cache_dir:
            return None
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        lock = self._cache_lock(key)
        deadline = time.monotonic() + CACHE_LOCK_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            try:
                descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    stream.write(json.dumps({"pid": os.getpid(), "created_at": time.time()}))
                return lock
            except FileExistsError:
                try:
                    age = time.time() - lock.stat().st_mtime
                    if age > CACHE_LOCK_STALE_SECONDS:
                        lock.unlink()
                        continue
                except OSError:
                    continue
                time.sleep(0.05)
            except OSError:
                return None
        return None

    @staticmethod
    def _release_cache_lock(lock: Path | None) -> None:
        if lock is None:
            return
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def _quarantine_cache_entry(self, entry: Path, reason: str) -> None:
        """Move a corrupt entry aside so it cannot poison future runs."""
        if not entry.exists() or not self.cache_dir:
            return
        quarantine = self.cache_dir / f".corrupt-{entry.name}-{time.time_ns()}"
        try:
            os.replace(entry, quarantine)
            atomic_write_text(quarantine / "quarantine-reason.txt", reason + "\n")
        except OSError:
            # A concurrent writer may have replaced the entry; a cache miss is
            # still safe and the next run will rebuild it.
            return

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
            self._quarantine_cache_entry(entry, "metadata unreadable")
            return None
        if (
            metadata.get("schema") != CACHE_SCHEMA
            or metadata.get("cache_key") != key
            or metadata.get("ok") is not True
            or metadata.get("local_code_fingerprint") != self.code_fingerprint
            or metadata.get("runtime_fingerprint") != self.runtime_fingerprint
        ):
            self._quarantine_cache_entry(entry, "cache metadata or environment fingerprint mismatch")
            return None
        artifacts = metadata.get("artifacts", [])
        if not isinstance(artifacts, list):
            self._quarantine_cache_entry(entry, "cache artifacts is not a list")
            return None
        safe_artifacts = []
        for artifact in artifacts:
            if not isinstance(artifact, dict) or not artifact.get("relative"):
                self._quarantine_cache_entry(entry, "cache artifact record invalid")
                return None
            relative = _safe_relative(artifact["relative"])
            if relative is None or artifact.get("kind") not in {"file", "directory"}:
                self._quarantine_cache_entry(entry, "cache artifact path invalid")
                return None
            source = entry / "artifacts" / relative
            if artifact["kind"] == "directory" and not source.is_dir():
                self._quarantine_cache_entry(entry, "cache directory artifact missing")
                return None
            if artifact["kind"] == "file" and not source.is_file():
                self._quarantine_cache_entry(entry, "cache file artifact missing")
                return None
            recorded_digest = artifact.get("sha256")
            if not isinstance(recorded_digest, str) or len(recorded_digest) != 64:
                self._quarantine_cache_entry(entry, "cache artifact digest invalid")
                return None
            try:
                current_digest = _artifact_digest(source)
            except OSError:
                self._quarantine_cache_entry(entry, "cache artifact unreadable")
                return None
            if current_digest != recorded_digest:
                self._quarantine_cache_entry(entry, "cache artifact digest mismatch")
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
        atomic_write_text(stdout_path, f"cache hit: {key}\n")
        atomic_write_text(stderr_path, "")
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
        # Static nodes encode a run-time condition (for example, a missing
        # required manifest) rather than an executable transformation.  Do
        # not cache them: otherwise a later run could replay an old condition
        # after the missing artifact has been repaired.
        if task.static_result is not None:
            return
        if self.mode != "dag" or not task.cacheable or not self.cache_dir or not result.get("ok"):
            return
        if not task.outputs:
            return
        artifacts = []
        for output in task.outputs:
            record = self._output_record(Path(output))
            if record is None:
                return
            artifacts.append(record)
        entry = self._cache_entry(key)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_dir / f".{key}.tmp-{os.getpid()}-{time.time_ns()}"
        lock = self._acquire_cache_lock(key)
        if lock is None:
            return
        try:
            if entry.exists():
                return
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
                "local_code_fingerprint": self.code_fingerprint,
                "runtime_fingerprint": self.runtime_fingerprint,
                "artifacts": artifacts,
                "result": cache_result,
            }
            atomic_write_json(temporary / "metadata.json", metadata)
            if entry.exists():
                shutil.rmtree(temporary)
            else:
                os.replace(temporary, entry)
        except OSError:
            shutil.rmtree(temporary, ignore_errors=True)
        finally:
            self._release_cache_lock(lock)

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
            # A static node is still a real pipeline node.  Materialize its
            # declared report/output so downstream aggregation cannot mistake
            # an in-memory failure result for a missing or stale artifact.
            atomic_write_text(stdout_path, str(result.get("stdout") or ""))
            atomic_write_text(stderr_path, str(result.get("stderr") or ""))
            result["stdout"] = str(stdout_path.resolve())
            result["stderr"] = str(stderr_path.resolve())
            report = result.get("report")
            for output in task.outputs:
                output = Path(output).resolve()
                if output.suffix.casefold() == ".json":
                    if not isinstance(report, dict):
                        report = {
                            "schema": "ai-ppt-plus/static-task-report/v1",
                            "task": task.name,
                            "valid": bool(result.get("ok")),
                            "status": "passed" if result.get("ok") else "blocked",
                            "issues": ([{"code": result.get("failure", "static_task_failed")}]
                                       if not result.get("ok") else []),
                        }
                    atomic_write_json(output, report)
                elif output.suffix:
                    atomic_write_text(output, str(result.get("failure") or ""))
        else:
            command = [sys.executable, *task.args]
            try:
                completed = subprocess.run(command, capture_output=True, text=True, timeout=task.timeout, check=False)
                stdout = as_text(completed.stdout)
                stderr = as_text(completed.stderr)
                exit_code = completed.returncode
                failure = None
            except subprocess.TimeoutExpired as exc:
                stdout = as_text(exc.stdout)
                stderr = as_text(exc.stderr) + f"\nstep timed out after {task.timeout}s"
                exit_code = 124
                failure = "timeout"
            except OSError as exc:
                stdout = ""
                stderr = f"{type(exc).__name__}: {exc}\n"
                exit_code = 127
                failure = "spawn-failed"
            atomic_write_text(stdout_path, stdout)
            atomic_write_text(stderr_path, stderr)
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
        atomic_write_text(stdout_path, "")
        atomic_write_text(stderr_path, "dependency failed; task was not executed\n")
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

    def _write_checkpoint(self, results: dict[str, dict[str, Any]], pending: set[str], *, status: str = "running") -> None:
        """Persist enough state to resume inspection after interruption."""
        checkpoint = {
            "schema": "ai-ppt-plus/pipeline-checkpoint/v1",
            "status": status,
            "run_dir": str(self.run_dir),
            "engine_version": ENGINE_VERSION,
            "local_code_fingerprint": self.code_fingerprint,
            "runtime_fingerprint": self.runtime_fingerprint,
            "completed": [
                {"name": name, "ok": result.get("ok"), "cache_hit": result.get("cache_hit"), "duration_ms": result.get("duration_ms", 0)}
                for name, result in results.items()
            ],
            "remaining": sorted(pending),
        }
        atomic_write_json(self.run_dir / "pipeline-checkpoint.json", checkpoint)

    def run(self) -> list[dict[str, Any]]:
        run_started = time.perf_counter()
        by_name = {task.name: task for task in self.tasks}
        order = {task.name: index for index, task in enumerate(self.tasks)}
        missing_deps = {
            task.name: [dep for dep in task.deps if dep not in by_name]
            for task in self.tasks
        }
        results: dict[str, dict[str, Any]] = {}
        pending = set(by_name)
        pool = None
        self._write_checkpoint(results, pending)
        try:
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
                    ready = sorted(ready, key=lambda item: order[item.name])
                    if self.max_workers == 1 or len(ready) == 1:
                        for task in ready:
                            failed = [dep for dep in task.deps if not results[dep].get("ok")]
                            results[task.name] = self._blocked_result(task, failed) if failed else self._run_task(task)
                            pending.remove(task.name)
                    else:
                        # Keep one pool for the complete run. Rebuilding a pool
                        # for every DAG wave paid a process/thread scheduling cost
                        # on the large validation graph without improving safety.
                        if pool is None:
                            pool = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="ppt-pipeline")
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
                    self._write_checkpoint(results, pending, status="blocked")
                    break
                self._write_checkpoint(results, pending)
        finally:
            if pool is not None:
                pool.shutdown(wait=True)
        self.last_wall_duration_ms = round((time.perf_counter() - run_started) * 1000, 3)
        self.last_cache_hits = sum(1 for result in results.values() if result.get("cache_hit") is True)
        self.last_cache_misses = sum(1 for result in results.values() if result.get("cache_hit") is False and result.get("failure") != "dependency_failed")
        critical_path: dict[str, float] = {}
        for task in self.tasks:
            own = float(results.get(task.name, {}).get("duration_ms", 0) or 0)
            dependency_path = max((critical_path.get(dep, 0.0) for dep in task.deps), default=0.0)
            critical_path[task.name] = dependency_path + own
        self.last_critical_path_ms = round(max(critical_path.values(), default=0.0), 3)
        self._write_checkpoint(results, set(), status="completed")
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
