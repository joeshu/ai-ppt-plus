#!/usr/bin/env python3
"""Build and validate the canonical cross-manifest registry.

The registry is the compatibility boundary between domain manifests. Input
manifests may keep their historical shapes, but the generated registry uses a
single SlideSpec/RegionSpec/ObjectSpec/AssetSpec vocabulary and validates the
references between those records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from manifest_contract import (
    EDITABILITY_LEVELS,
    MODEL_NAME,
    MODEL_VERSION,
    canonical_asset,
    canonical_bbox,
    canonical_object,
    canonical_region,
    canonical_text_spec,
    first,
    valid_sha256,
)
from text_model import build_manifest as build_text_manifest, validate_manifest as validate_text_manifest


SCHEMA = "ai-ppt-plus/manifest-registry/v2"
LEGACY_SCHEMAS = {"ai-ppt-plus/manifest-registry/v1"}
VALIDATION_SCHEMA = "ai-ppt-plus/manifest-registry-validation/v2"


def load(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path: str | Path) -> str:
    value = Path(path)
    result = hashlib.sha256()
    with value.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def path_ref(path: str | Path, base: str | Path) -> str:
    value, root = Path(path).resolve(), Path(base).resolve()
    try:
        return str(value.relative_to(root))
    except ValueError:
        return str(value)


def items_from(data: Any, keys: tuple[str, ...]) -> list[Any]:
    if not isinstance(data, dict):
        return []
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def _slide_entries(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    raw = data.get("slides")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _slide_number(slide: dict[str, Any], index: int) -> int:
    value = slide.get("slide_no", index)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"slide number is invalid at index {index}: {value!r}") from exc


def _by_slide(data: Any) -> dict[int, dict[str, Any]]:
    return {_slide_number(slide, index): slide for index, slide in enumerate(_slide_entries(data), 1)}


def _resolve_path(value: Any, path_base: Any, base: Path) -> Path | None:
    if not isinstance(value, str) or not value or value.startswith("native:"):
        return None
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    if isinstance(path_base, str) and path_base:
        parent = Path(path_base)
        if not parent.is_absolute():
            parent = base / parent
    else:
        parent = base
    return (parent / candidate).resolve()


def _asset_path_base(manifest_path: str | Path, base: Path) -> str:
    return path_ref(Path(manifest_path).resolve().parent, base)


def _source_record(source_id: str, path: str | Path, base: Path, *, kind: str, required: bool = True) -> dict[str, Any]:
    value = Path(path).resolve()
    return {
        "source_id": source_id,
        "kind": kind,
        "path": path_ref(value, base),
        "sha256": digest(value),
        "required": required,
    }


def _canonical_text_specs(raw_specs: Any, slide_no: int) -> list[dict[str, Any]]:
    if not isinstance(raw_specs, list):
        return []
    return [canonical_text_spec(item, slide_no, index) for index, item in enumerate(raw_specs, 1) if isinstance(item, dict)]


def _text_specs_from_objects(objects: list[dict[str, Any]], slide_no: int) -> list[dict[str, Any]]:
    specs = []
    for index, obj in enumerate(objects, 1):
        details = obj.get("details") if isinstance(obj.get("details"), dict) else {}
        candidate = details.get("text_spec")
        if not isinstance(candidate, dict) and obj.get("object_type") == "editable_text":
            candidate = details if any(key in details for key in ("text", "content", "runs")) else None
        if isinstance(candidate, dict):
            specs.append(canonical_text_spec(candidate, slide_no, index))
    return specs


def build(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    base = output.parent
    slide_path = Path(args.slide_manifest).resolve()
    slide_data = load(slide_path)
    if not isinstance(slide_data, dict) or not _slide_entries(slide_data):
        raise ValueError("slide manifest must contain non-empty slides[]")
    object_path = Path(args.object_manifest).resolve() if args.object_manifest else None
    object_data = load(object_path) if object_path else {}
    layout_path = Path(args.layout).resolve() if args.layout else None
    layout_data = load(layout_path) if layout_path else {}
    text_path = Path(args.text_manifest).resolve() if args.text_manifest else None
    text_data = load(text_path) if text_path else (build_text_manifest(layout_data) if layout_data else {})

    object_by_slide = _by_slide(object_data)
    layout_by_slide = _by_slide(layout_data)
    text_by_slide = _by_slide(text_data)
    object_source = path_ref(object_path, base) if object_path else path_ref(slide_path, base)
    layout_source = path_ref(layout_path, base) if layout_path else "layout.json"

    sources = [_source_record("slide_manifest", slide_path, base, kind="manifest")]
    if object_path:
        sources.append(_source_record("object_manifest", object_path, base, kind="manifest"))
    if layout_path:
        sources.append(_source_record("layout", layout_path, base, kind="layout"))
    if text_path:
        sources.append(_source_record("text_manifest", text_path, base, kind="manifest"))
    for index, manifest_path in enumerate(args.asset_manifest, 1):
        sources.append(_source_record(f"asset_manifest_{index:02d}", manifest_path, base, kind="asset-manifest"))
    if args.report_index:
        sources.append(_source_record("report_index", args.report_index, base, kind="report-index", required=False))

    assets = []
    asset_manifest_refs = []
    for index, manifest_path in enumerate(args.asset_manifest, 1):
        asset_path = Path(manifest_path).resolve()
        data = load(asset_path)
        source = path_ref(asset_path, base)
        path_base = _asset_path_base(asset_path, base)
        asset_manifest_refs.append(source)
        for item_index, item in enumerate(items_from(data, ("assets", "panels", "icons")), 1):
            if not isinstance(item, dict):
                continue
            asset = canonical_asset(item, source, path_base, item_index)
            resolved = _resolve_path(asset.get("path"), asset.get("path_base"), base)
            if resolved and resolved.is_file():
                asset["path_sha256"] = digest(resolved)
            asset["asset_manifest_index"] = index
            assets.append(asset)

    slides = []
    for index, raw_slide in enumerate(_slide_entries(slide_data), 1):
        number = _slide_number(raw_slide, index)
        layout = layout_by_slide.get(number, {})
        object_slide = object_by_slide.get(number, {})
        source_objects = object_slide.get("objects") if isinstance(object_slide.get("objects"), list) else raw_slide.get("objects")
        source_objects = source_objects if isinstance(source_objects, list) else []
        normalized_objects = [
            canonical_object(item, number, object_index, object_source)
            for object_index, item in enumerate(source_objects, 1)
            if isinstance(item, dict)
        ]

        region_items = layout.get("regions", layout.get("panels", []))
        if not isinstance(region_items, list):
            region_items = raw_slide.get("regions", raw_slide.get("panels", []))
        regions = [
            region
            for region_index, item in enumerate(region_items if isinstance(region_items, list) else [], 1)
            if isinstance(item, dict)
            for region in [canonical_region(item, number, region_index)]
            if region is not None
        ]

        text_slide = text_by_slide.get(number, {})
        text_specs = _canonical_text_specs(text_slide.get("text_specs"), number)
        if not text_specs:
            text_specs = _text_specs_from_objects(normalized_objects, number)
        text_runs = [run for spec in text_specs for run in spec.get("runs", [])]

        asset_ids = []
        for value in raw_slide.get("asset_ids", []):
            if value not in (None, "") and str(value) not in asset_ids:
                asset_ids.append(str(value))
        for region in regions:
            for value in region.get("asset_ids", []):
                if value not in asset_ids:
                    asset_ids.append(value)
        for obj in normalized_objects:
            for value in obj.get("asset_ids", []):
                if value not in asset_ids:
                    asset_ids.append(value)

        slide_id = first(raw_slide, "slide_id", "id") or f"S{number:02d}"
        slides.append({
            "slide_id": str(slide_id),
            "slide_no": number,
            "page_type": raw_slide.get("page_type"),
            "state": raw_slide.get("state", slide_data.get("state", args.state)),
            "geometry": {"source_ref": layout_source, "coordinate_space": layout_data.get("units")} if isinstance(layout_data, dict) else {"source_ref": layout_source},
            "geometry_ref": first(raw_slide, "layout_ref", "reference_image") or layout_source,
            "regions": regions,
            "objects": normalized_objects,
            "text_specs": text_specs,
            "text_runs": text_runs,
            "asset_ids": asset_ids,
            "gate_refs": raw_slide.get("gate_refs", []),
        })

    report_index_ref = path_ref(args.report_index, base) if args.report_index else None
    gates = []
    if args.report_index:
        report_data = load(args.report_index)
        for index, entry in enumerate(report_data.get("reports", []) if isinstance(report_data, dict) else [], 1):
            if not isinstance(entry, dict):
                continue
            gate = dict(entry)
            gate["gate_id"] = str(first(entry, "gate_id", "report_type", "id") or f"gate-{index:02d}")
            gate["source"] = report_index_ref
            gates.append(gate)

    registry = {
        "schema": SCHEMA,
        "model": {"name": MODEL_NAME, "version": MODEL_VERSION, "legacy_inputs": sorted(LEGACY_SCHEMAS)},
        "project_id": args.project_id,
        "revision": args.revision,
        "state": args.state,
        "deck": {"path": path_ref(args.deck, base), "sha256": digest(args.deck)},
        "authority": {
            "formal_content": args.formal_content_source,
            "visual": args.visual_source,
            "geometry": layout_source,
            "semantic_objects": object_source,
            "assets": asset_manifest_refs,
        },
        "sources": sources,
        "slides": slides,
        "assets": assets,
        "gates": gates,
        "evidence": {
            "slide_manifest": path_ref(slide_path, base),
            "object_manifest": path_ref(object_path, base) if object_path else None,
            "layout": path_ref(layout_path, base) if layout_path else None,
            "text_manifest": path_ref(text_path, base) if text_path else None,
            "asset_manifests": asset_manifest_refs,
            "report_index": report_index_ref,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, "output": str(output), "slides": len(slides), "assets": len(assets), "model": MODEL_NAME}, ensure_ascii=False))
    return 0


def _resolve_registry_ref(value: Any, base: Path) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = Path(value)
    return candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()


def _bbox_valid(value: Any) -> bool:
    box = canonical_bbox(value)
    return bool(box and box["w"] > 0 and box["h"] > 0 and box["x"] >= 0 and box["y"] >= 0)


def _polygon_valid(value: Any) -> bool:
    if not isinstance(value, list) or len(value) < 3:
        return False
    return all(
        isinstance(point, list)
        and len(point) == 2
        and all(isinstance(part, (int, float)) and not isinstance(part, bool) for part in point)
        for point in value
    )


def _refs(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return []


def _region_refs(region: dict[str, Any], key: str, *legacy_keys: str) -> list[str]:
    refs = _refs(region.get(key))
    if refs:
        return refs
    for legacy_key in legacy_keys:
        value = region.get(legacy_key)
        if value not in (None, ""):
            return [str(value)]
    return []


def _text_model_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Adapt the registry geometry shape to the TextSpec validator shape."""
    result = dict(spec)
    bbox = canonical_bbox(result.get("bbox"))
    if bbox is not None:
        result["bbox"] = bbox
    source_bbox = result.get("source_bbox")
    if isinstance(source_bbox, dict):
        result["source_bbox"] = [source_bbox[key] for key in ("x", "y", "w", "h")]
    return result


def _validate_text_specs(text_specs: list[Any], slide_no: Any, issues: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    adapted = [_text_model_spec(spec) for spec in text_specs if isinstance(spec, dict)]
    result = validate_text_manifest({
        "schema": "ai-ppt-plus/text-layout-manifest/v1",
        "units": "fraction",
        "reference_size": {},
        "slides": [{"slide_no": slide_no, "text_specs": adapted}],
    })
    for issue in result.get("issues", []):
        _append_issue(
            issues,
            "text_model_" + str(issue.get("code", "invalid")),
            slide_no=slide_no,
            **{key: value for key, value in issue.items() if key != "code"},
        )
    for warning in result.get("warnings", []):
        warnings.append({
            "code": "text_model_" + str(warning.get("code", "warning")),
            "slide_no": slide_no,
            **{key: value for key, value in warning.items() if key != "code"},
        })


def _append_issue(issues: list[dict[str, Any]], code: str, **details: Any) -> None:
    issues.append({"code": code, **details})


def _validate_source_records(data: dict[str, Any], registry_path: Path, issues: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    sources = data.get("sources")
    if not isinstance(sources, list):
        _append_issue(issues, "sources_not_array")
        return
    source_ids = set()
    for source in sources:
        if not isinstance(source, dict):
            _append_issue(issues, "invalid_source_record")
            continue
        source_id = source…6421 tokens truncated…ear`` uses one worker and disables the cache.  ``mode=dag``
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
            recorded_digest = artifact.get("sha256")
            if not isinstance(recorded_digest, str) or len(recorded_digest) != 64:
                return None
            try:
                current_digest = _artifact_digest(source)
            except OSError:
                return None
            if current_digest != recorded_digest:
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
        run_started = time.perf_counter()
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
        self.last_wall_duration_ms = round((time.perf_counter() - run_started) * 1000, 3)
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