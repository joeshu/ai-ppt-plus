#!/usr/bin/env python3
"""Register one native raster-generation result in a visual manifest.

The helper copies the untouched generated source into the project, records
actual dimensions and hashes, and replaces a page only when ``--force`` is
explicitly supplied for a page-local retry. It does not draw, resize, or edit
the raster.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from atomic_output import atomic_copy, atomic_write_json


MANIFEST_SCHEMA = "ai-ppt-plus/visual-generation-manifest/v1"
CONTINUITY_STATUSES = {"preserved", "shared-anchor", "degraded", "unknown"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_existing(value: str, base: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    from_cwd = (Path.cwd() / candidate).resolve()
    from_base = (base / candidate).resolve()
    return from_cwd if from_cwd.is_file() else from_base


def resolve_inside(root: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path must stay inside manifest root: {value}") from exc
    return resolved


def raster_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError(f"Pillow is required to inspect the generated raster: {exc}") from exc
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            if not width or not height:
                raise ValueError("raster has an empty canvas")
            return int(width), int(height)
    except Exception as exc:
        raise ValueError(f"generated source is not a decodable raster: {exc}") from exc


def ratio_label(size: tuple[int, int]) -> str:
    width, height = size
    ratio = width / height
    if abs(ratio - (16 / 9)) <= 0.02:
        return "16:9"
    if abs(ratio - (3 / 2)) <= 0.02:
        return "3:2"
    raise ValueError(f"unsupported raster ratio: {width}:{height}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--slide-no", type=int, required=True)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--source", required=True, help="original generated raster path")
    parser.add_argument("--copy-to", required=True, help="project-relative raster path")
    parser.add_argument("--backend", required=True)
    parser.add_argument("--model-or-tool", required=True)
    parser.add_argument("--session-id")
    parser.add_argument("--context-continuity-status", choices=sorted(CONTINUITY_STATUSES), default="preserved")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--retry-trigger")
    parser.add_argument("--force", action="store_true", help="replace an existing page record for a page-local retry")
    parser.add_argument("--report")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.is_file():
        raise SystemExit(f"manifest missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"manifest invalid: {type(exc).__name__}: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise SystemExit("manifest schema must be ai-ppt-plus/visual-generation-manifest/v1")
    if args.slide_no < 1 or args.attempt < 1:
        raise SystemExit("slide number and attempt must be positive")

    root = manifest_path.parent
    source = resolve_existing(args.source, root)
    if not source.is_file():
        raise SystemExit(f"generated source missing: {source}")
    prompt = resolve_existing(args.prompt_file, root)
    if not prompt.is_file():
        raise SystemExit(f"prompt file missing: {prompt}")
    target = resolve_inside(root, args.copy_to)
    if source == target:
        raise SystemExit("generated source and project copy must be distinct")

    records = manifest.get("slides")
    if not isinstance(records, list):
        raise SystemExit("manifest slides must be a list")
    existing = next((item for item in records if isinstance(item, dict) and item.get("slide_no") == args.slide_no), None)
    if existing is not None and not args.force:
        raise SystemExit(f"slide {args.slide_no} already exists; use --force only for a page-local retry")

    size = raster_size(source)
    ratio = ratio_label(size)
    atomic_copy(source, target)
    prompt_relative = prompt.relative_to(root).as_posix()
    target_relative = target.relative_to(root).as_posix()
    record = {
        "slide_no": args.slide_no,
        "prompt_file": prompt_relative,
        "prompt_sha256": sha256(prompt),
        "generated_source": str(source),
        "copied_to": target_relative,
        "generated_source_sha256": sha256(source),
        "copied_to_sha256": sha256(target),
        "backend": args.backend,
        "model_or_tool": args.model_or_tool,
        "generation_session_id": args.session_id or manifest.get("generation_session_id", ""),
        "context_continuity_status": args.context_continuity_status,
        "attempt": args.attempt,
        "canvas": {"width_px": size[0], "height_px": size[1], "ratio": ratio},
    }
    if args.retry_trigger:
        record["retry_trigger"] = args.retry_trigger
    updated_records = [item for item in records if not (isinstance(item, dict) and item.get("slide_no") == args.slide_no)]
    updated_records.append(record)
    updated_records.sort(key=lambda item: item.get("slide_no", 0) if isinstance(item, dict) else 0)
    updated_manifest = dict(manifest)
    updated_manifest["slides"] = updated_records
    atomic_write_json(manifest_path, updated_manifest)
    result = {
        "schema": "ai-ppt-visual-gen/register-generated-slide/v1",
        "valid": True,
        "manifest": str(manifest_path),
        "slide_no": args.slide_no,
        "copied_to": str(target),
        "canvas": record["canvas"],
        "attempt": args.attempt,
        "replaced_existing": existing is not None,
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
