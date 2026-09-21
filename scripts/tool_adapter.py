#!/usr/bin/env python3
"""Validated, observable adapters for the PPTX toolchain.

The reconstruction workers intentionally keep authoring logic in JavaScript
and ``@oai/artifact-tool``.  This module owns the boring but failure-prone
edges around them: runtime discovery, path validation, numeric/style checks,
resource preloading, bounded retries and staging publication.  It never
invokes a shell and it never overwrites a validated deliverable.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
from typing import Any, Callable, Iterable, Mapping, Sequence

from atomic_output import atomic_copy


SCHEMA = "ai-ppt-plus/tool-adapter/v1"
MAX_RETRIES = 2
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{3,8}$")
_RGB_COLOR = re.compile(r"^rgba?\([^)]*\)$", re.IGNORECASE)
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
_CSS_COLORS = {"black", "white", "red", "blue", "green", "yellow", "orange", "purple", "gray", "grey", "transparent", "none", "currentcolor"}


class AdapterError(ValueError):
    """A deterministic input/output contract error."""


@dataclass(frozen=True)
class RuntimePaths:
    node: str | None = None
    node_modules: str | None = None
    artifact_tool: str | None = None
    skia: str | None = None
    font_library: str | None = None
    finalizer: str | None = None
    render_helper: str | None = None
    python: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["artifact_tool_available"] = bool(self.artifact_tool)
        result["node_modules_available"] = bool(self.node_modules)
        return result


@dataclass
class CommandLog:
    phase: str
    tool: str
    command: list[str]
    input_sha256: str | None
    duration_ms: float
    exit_code: int | None
    error_class: str | None
    retry_count: int
    outputs: dict[str, str]
    stdout: str = ""
    stderr: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _env_path(env: Mapping[str, str], name: str, *, directory: bool = False) -> Path | None:
    raw = env.get(name)
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        return None
    if directory and not candidate.is_dir():
        return None
    if not directory and not candidate.is_file():
        return None
    return candidate.resolve()


def discover_runtime(*, skill_dir: str | Path | None = None, env: Mapping[str, str] | None = None) -> RuntimePaths:
    """Discover only existing, absolute runtime paths.

    Environment values are hints, never trust boundaries.  Every accepted
    value is absolute and exists; otherwise a verified PATH or skill-local
    candidate is used.  Missing Artifact Tool is represented explicitly so a
    caller can fail before authoring instead of silently selecting a Python
    backend.
    """
    environment = dict(os.environ if env is None else env)
    root = Path(skill_dir).resolve() if skill_dir else Path(__file__).resolve().parents[1]
    node = _env_path(environment, "RUNTIME_NODE") or (Path(shutil.which("node")).resolve() if shutil.which("node") else None)
    python = _env_path(environment, "RUNTIME_PYTHON") or Path(sys.executable).resolve()
    modules = _env_path(environment, "RUNTIME_NODE_MODULES", directory=True)
    if modules is None:
        for candidate in (root / "node_modules", root.parent / "node_modules"):
            if candidate.is_dir():
                modules = candidate.resolve()
                break
    artifact = None
    if modules:
        package = modules / "@oai" / "artifact-tool"
        if package.is_dir():
            artifact = package
    finalizer = _env_path(environment, "RUNTIME_FINALIZER")
    if finalizer is None:
        for candidate in (root / "container_tools" / "finalize_presentation.mjs", root / "scripts" / "finalize_presentation.mjs"):
            if candidate.is_file():
                finalizer = candidate.resolve()
                break
    render_helper = _env_path(environment, "RUNTIME_RENDER_HELPER")
    if render_helper is None:
        candidate = root / "scripts" / "render_authoritative.py"
        if not candidate.is_file():
            candidate = root / "scripts" / "render_pptx.py"
        render_helper = candidate.resolve() if candidate.is_file() else None
    skia = _env_path(environment, "RUNTIME_SKIA", directory=True)
    font_library = _env_path(environment, "RUNTIME_FONT_LIBRARY", directory=True)
    return RuntimePaths(
        node=str(node) if node else None,
        node_modules=str(modules) if modules else None,
        artifact_tool=str(artifact) if artifact else None,
        skia=str(skia) if skia else None,
        font_library=str(font_library) if font_library else None,
        finalizer=str(finalizer) if finalizer else None,
        render_helper=str(render_helper) if render_helper else None,
        python=str(python) if python else None,
    )


def normalize_path(
    value: str | Path,
    *,
    base_dir: str | Path,
    kind: str = "input",
    must_exist: bool = False,
    allowed_roots: Iterable[str | Path] = (),
) -> Path:
    """Return one canonical path and reject traversal/ambiguous output paths."""
    if value is None or not str(value).strip():
        raise AdapterError(f"{kind}_path_empty")
    raw = Path(value).expanduser()
    candidate = raw.resolve() if raw.is_absolute() else (Path(base_dir).resolve() / raw).resolve()
    if any(part in {"", ".", ".."} for part in raw.parts):
        raise AdapterError(f"{kind}_path_traversal: {value}")
    if must_exist and not candidate.exists():
        raise AdapterError(f"{kind}_missing: {candidate}")
    roots = [Path(item).resolve() for item in allowed_roots]
    if kind == "output":
        if not roots:
            raise AdapterError("output_roots_required")
        if not any(candidate == root or root in candidate.parents for root in roots):
            raise AdapterError(f"output_outside_controlled_root: {candidate}")
    return candidate


def validate_finite(value: Any, *, field: str = "value", minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise AdapterError(f"{field}_must_be_finite")
    number = float(value)
    if minimum is not None and number < minimum:
        raise AdapterError(f"{field}_below_minimum:{minimum}")
    return number


def validate_geometry(payload: Mapping[str, Any], *, field: str = "geometry") -> None:
    """Validate numeric geometry recursively without changing caller data."""
    numeric_fields = {"left", "top", "right", "bottom", "width", "height", "fontSize", "fontSizePt", "margin", "padding", "opacity", "transparency"}
    for key, value in payload.items():
        if key in numeric_fields:
            if value is None:
                continue
            minimum = 0.0 if key in {"width", "height", "fontSize", "fontSizePt", "margin", "padding"} else None
            validate_finite(value, field=f"{field}.{key}", minimum=minimum)
        elif isinstance(value, Mapping):
            validate_geometry(value, field=f"{field}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, Mapping):
                    validate_geometry(item, field=f"{field}.{key}[{index}]")


def validate_color(value: str, *, field: str = "color") -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(f"{field}_invalid")
    candidate = value.strip()
    if candidate.lower() in {"none", "transparent"} or _HEX_COLOR.fullmatch(candidate) or _RGB_COLOR.fullmatch(candidate):
        return candidate
    if _SAFE_NAME.fullmatch(candidate) and candidate.lower() in _CSS_COLORS:
        return candidate
    raise AdapterError(f"{field}_invalid")


def validate_enum(value: Any, allowed: Iterable[str], *, field: str = "enum") -> str:
    values = set(allowed)
    if not isinstance(value, str) or value not in values:
        raise AdapterError(f"{field}_invalid:{value}")
    return value


def preload_files(paths: Iterable[str | Path]) -> dict[str, dict[str, Any]]:
    """Read every binary resource before authoring and return hash evidence."""
    loaded: dict[str, dict[str, Any]] = {}
    for raw in paths:
        path = Path(raw).resolve()
        if not path.is_file():
            raise AdapterError(f"resource_missing: {path}")
        payload = path.read_bytes()
        loaded[str(path)] = {"sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}
    return loaded


def create_staging_dir(root: str | Path, *, run_id: str | None = None) -> Path:
    """Create one unique, controlled staging directory for a run."""
    base = Path(root).resolve()
    base.mkdir(parents=True, exist_ok=True)
    token = run_id or f"run-{uuid.uuid4().hex}"
    if not _SAFE_NAME.fullmatch(token):
        raise AdapterError("run_id_invalid")
    staging = base / token
    staging.mkdir()
    return staging


def classify_failure(*, returncode: int | None = None, stderr: str = "", exc: BaseException | None = None) -> str | None:
    text = f"{stderr} {exc or ''}".lower()
    if isinstance(exc, subprocess.TimeoutExpired) or "timed out" in text or "timeout" in text:
        return "timeout"
    if isinstance(exc, FileNotFoundError):
        return "tool-unavailable"
    if isinstance(exc, OSError) and returncode is None:
        return "spawn-failed"
    if any(token in text for token in ("sharing violation", "temporarily unavailable", "resource busy", "connection reset")):
        return "transient"
    if any(token in text for token in ("destination already exists", "output conflict", "file exists")):
        return "output-conflict"
    if any(token in text for token in ("ooxml", "presentationml", "zipfile", "invalid pptx")):
        return "ooxml-error"
    if any(token in text for token in ("nan", "infinity", "invalid color", "missing text", "content error")):
        return "content-error"
    if returncode not in (None, 0):
        return "tool-error"
    return None


def _digest_inputs(paths: Iterable[str | Path]) -> str | None:
    records = []
    for raw in sorted({str(Path(item).resolve()) for item in paths}):
        path = Path(raw)
        if not path.is_file():
            records.append({"path": raw, "missing": True})
        else:
            records.append({"path": raw, "sha256": sha256(path), "size": path.stat().st_size})
    if not records:
        return None
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()


def run_command(
    command: Sequence[str | Path],
    *,
    phase: str,
    tool: str,
    inputs: Iterable[str | Path] = (),
    outputs: Iterable[str | Path] = (),
    timeout_seconds: int = 600,
    max_retries: int = 0,
    retryable: Iterable[str] = ("timeout", "spawn-failed", "transient"),
    cwd: str | Path | None = None,
    log: list[dict[str, Any]] | None = None,
) -> CommandLog:
    """Execute an argv list with bounded, classified retries and evidence."""
    argv = [str(item) for item in command]
    if not argv:
        raise AdapterError("command_empty")
    retry_limit = min(MAX_RETRIES, max(0, int(max_retries)))
    allowed_retries = set(retryable)
    input_digest = _digest_inputs(inputs)
    started = time.perf_counter()
    attempt = 0
    stdout = stderr = ""
    exit_code: int | None = None
    failure: str | None = None
    while True:
        attempt_started = time.perf_counter()
        try:
            completed = subprocess.run(argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout_seconds, check=False, shell=False)
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            exit_code = completed.returncode
            failure = classify_failure(returncode=exit_code, stderr=stderr)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            exit_code = 124
            failure = "timeout"
        except OSError as exc:
            stdout = ""
            stderr = f"{type(exc).__name__}: {exc}"
            exit_code = 127
            failure = classify_failure(returncode=None, stderr=stderr, exc=exc)
        if not failure or attempt >= retry_limit or failure not in allowed_retries:
            break
        attempt += 1
        time.sleep(0.05 * (2 ** (attempt - 1)))
    output_hashes = {}
    for raw in outputs:
        path = Path(raw)
        if path.is_file():
            output_hashes[str(path.resolve())] = sha256(path)
    record = CommandLog(phase=phase, tool=tool, command=argv, input_sha256=input_digest,
                        duration_ms=round((time.perf_counter() - started) * 1000, 3),
                        exit_code=exit_code, error_class=failure, retry_count=attempt,
                        outputs=output_hashes, stdout=stdout, stderr=stderr)
    if log is not None:
        log.append(record.as_dict())
    return record


def publish_staged(source: str | Path, target: str | Path, *, staging_root: str | Path, deliverables_root: str | Path) -> Path:
    """Promote one validated staging artifact without silently making r2 files."""
    source_path = normalize_path(source, base_dir=staging_root, kind="input", must_exist=True)
    if not source_path.is_file():
        raise AdapterError("staged_source_not_file")
    target_path = normalize_path(target, base_dir=deliverables_root, kind="output", allowed_roots=(deliverables_root,))
    staging = Path(staging_root).resolve()
    if staging != source_path and staging not in source_path.parents:
        raise AdapterError("staged_source_outside_staging_root")
    if target_path.exists():
        raise AdapterError(f"output_conflict: {target_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    return atomic_copy(source_path, target_path)


def detect_full_page_image(objects: Iterable[Mapping[str, Any]], *, slide_width: float, slide_height: float, threshold: float = 0.85) -> list[dict[str, Any]]:
    """Flag suspicious image coverage while preserving legitimate small assets."""
    validate_finite(slide_width, field="slide_width", minimum=0.000001)
    validate_finite(slide_height, field="slide_height", minimum=0.000001)
    validate_finite(threshold, field="threshold", minimum=0.0)
    slide_area = float(slide_width) * float(slide_height)
    findings = []
    for item in objects:
        if str(item.get("object_type", "")).lower() not in {"image", "raster_image", "picture"}:
            continue
        geometry = item.get("geometry") if isinstance(item.get("geometry"), Mapping) else item
        area = validate_finite(geometry.get("width"), field="image.width", minimum=0) * validate_finite(geometry.get("height"), field="image.height", minimum=0)
        coverage = area / slide_area if slide_area else 1.0
        if coverage >= threshold:
            findings.append({"object_id": item.get("object_id"), "coverage": round(coverage, 6), "threshold": threshold})
    return findings


def check_arrow_collisions(arrows: Iterable[Mapping[str, Any]], text_boxes: Iterable[Mapping[str, Any]], *, padding: float = 0.0) -> list[dict[str, Any]]:
    """Detect axis-aligned connector/text intersections before export."""
    validate_finite(padding, field="padding", minimum=0)

    def box(item: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
        geometry = item.get("geometry") if isinstance(item.get("geometry"), Mapping) else item
        left = validate_finite(geometry.get("left"), field="left")
        top = validate_finite(geometry.get("top"), field="top")
        width = validate_finite(geometry.get("width"), field="width", minimum=0)
        height = validate_finite(geometry.get("height"), field="height", minimum=0)
        return left - padding, top - padding, left + width + padding, top + height + padding

    findings = []
    for arrow in arrows:
        abox = box(arrow)
        if not abox:
            continue
        for text_box in text_boxes:
            tbox = box(text_box)
            if not tbox:
                continue
            if abox[0] < tbox[2] and abox[2] > tbox[0] and abox[1] < tbox[3] and abox[3] > tbox[1]:
                findings.append({"arrow_id": arrow.get("object_id"), "text_id": text_box.get("object_id")})
    return findings


def validate_overlay_bindings(bindings: Iterable[Mapping[str, Any]]) -> None:
    """Require deterministic table-cell ownership for text overlays."""
    seen: set[tuple[str, int, int]] = set()
    for item in bindings:
        table_id = item.get("table_id")
        row = item.get("row")
        column = item.get("column")
        overlay_id = item.get("overlay_id")
        if not isinstance(table_id, str) or not table_id or not isinstance(overlay_id, str) or not overlay_id:
            raise AdapterError("overlay_binding_identity_missing")
        if not isinstance(row, int) or row < 0 or not isinstance(column, int) or column < 0:
            raise AdapterError("overlay_binding_cell_invalid")
        key = (table_id, row, column)
        if key in seen:
            raise AdapterError(f"overlay_binding_duplicate:{table_id}:{row}:{column}")
        seen.add(key)
