#!/usr/bin/env python3
"""Build a neutral contact sheet for visual-generation A5 review.

The output is a QA contact sheet made only from the generated/copied raster
pages listed in ``visual-generation-manifest.json``.  It is not a slide, does
not alter any source image, and never enters PPTX composition or
image-to-editable-PPTX reconstruction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from atomic_output import atomic_replace, atomic_write_json
from validate_visual_generation_plan import MANIFEST_SCHEMA, resolve_path, text_value, validate_image


STRIP_SCHEMA = "ai-ppt-plus/visual-deck-strip/v1"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_issue(issues: list[dict], code: str, **details) -> None:
    item = {"severity": "blocker", "code": code}
    item.update(details)
    issues.append(item)


def ratio_value(value: str) -> float | None:
    return {"16:9": 16 / 9, "3:2": 3 / 2}.get(value)


def inside(root: Path, path: Path) -> bool:
    return path == root or root in path.parents


def make_sheet(images: list[tuple[int, Path, tuple[int, int]]], columns: int, padding: int, thumbnail_width: int):
    from PIL import Image, ImageOps

    first_width, first_height = images[0][2]
    deck_ratio = first_width / first_height if first_height else 16 / 9
    thumbnail_height = max(1, round(thumbnail_width / deck_ratio))
    rows = math.ceil(len(images) / columns)
    sheet_width = columns * thumbnail_width + (columns + 1) * padding
    sheet_height = rows * thumbnail_height + (rows + 1) * padding
    sheet = Image.new("RGB", (sheet_width, sheet_height), (238, 241, 244))
    for index, (_slide_no, path, _size) in enumerate(images):
        row, column = divmod(index, columns)
        with Image.open(path) as source:
            image = ImageOps.contain(source.convert("RGB"), (thumbnail_width, thumbnail_height), Image.Resampling.LANCZOS)
        cell = Image.new("RGB", (thumbnail_width, thumbnail_height), (255, 255, 255))
        cell.paste(image, ((thumbnail_width - image.width) // 2, (thumbnail_height - image.height) // 2))
        x = padding + column * (thumbnail_width + padding)
        y = padding + row * (thumbnail_height + padding)
        sheet.paste(cell, (x, y))
    return sheet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="visual-generation-manifest.json")
    parser.add_argument("--output", required=True, help="QA contact-sheet PNG path")
    parser.add_argument("--expected-pages", type=int)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--padding", type=int, default=24)
    parser.add_argument("--thumbnail-width", type=int, default=512)
    parser.add_argument("--record-in-manifest", action="store_true", help="record the strip and source hashes in the manifest")
    parser.add_argument("--force", action="store_true", help="allow replacing an existing strip/record")
    parser.add_argument("--report")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    output_path = Path(args.output).resolve()
    issues: list[dict] = []
    if args.columns < 1 or args.columns > 6:
        add_issue(issues, "columns_invalid", observed=args.columns, allowed="1..6")
    if args.padding < 0 or args.thumbnail_width < 64:
        add_issue(issues, "strip_dimensions_invalid")
    if not manifest_path.is_file():
        add_issue(issues, "manifest_missing", path=str(manifest_path))
        manifest = {}
    else:
        try:
            manifest = read_json(manifest_path)
        except Exception as exc:
            add_issue(issues, "manifest_invalid_json", message=f"{type(exc).__name__}: {exc}")
            manifest = {}
    if manifest.get("schema") != MANIFEST_SCHEMA:
        add_issue(issues, "manifest_schema_invalid", observed=manifest.get("schema"))
    if not inside(manifest_path.parent, output_path):
        add_issue(issues, "output_outside_manifest_root", path=str(output_path))
    if output_path == manifest_path:
        add_issue(issues, "output_conflicts_with_manifest", path=str(output_path))
    if output_path.suffix.lower() != ".png":
        add_issue(issues, "output_extension_invalid", observed=output_path.suffix)
    records = manifest.get("slides") if isinstance(manifest.get("slides"), list) else []
    if not records:
        add_issue(issues, "manifest_slides_missing")
    valid_records: list[tuple[int, Path, tuple[int, int], dict]] = []
    seen: set[int] = set()
    expected_ratio: float | None = None
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            add_issue(issues, "manifest_slide_invalid", index=index)
            continue
        slide_no = record.get("slide_no")
        if not isinstance(slide_no, int) or slide_no < 1:
            add_issue(issues, "manifest_slide_number_invalid", index=index)
            continue
        if slide_no in seen:
            add_issue(issues, "manifest_slide_duplicate", slide_no=slide_no)
            continue
        seen.add(slide_no)
        copied_path = resolve_path(manifest_path.parent, record.get("copied_to"))
        if copied_path is None or not copied_path.is_file():
            add_issue(issues, "copied_slide_missing", slide_no=slide_no, path=str(copied_path) if copied_path else None)
            continue
        valid_image, size, error = validate_image(copied_path)
        if not valid_image or not size:
            add_issue(issues, "copied_slide_decode_failed", slide_no=slide_no, message=error)
            continue
        canvas = record.get("canvas") if isinstance(record.get("canvas"), dict) else {}
        ratio = ratio_value(text_value(canvas.get("ratio")))
        if ratio is not None:
            observed_ratio = size[0] / size[1] if size[1] else 0
            if abs(observed_ratio - ratio) > 0.02:
                add_issue(issues, "copied_slide_ratio_mismatch", slide_no=slide_no, expected=canvas.get("ratio"), observed=list(size))
            if expected_ratio is None:
                expected_ratio = ratio
        valid_records.append((slide_no, copied_path, size, record))
    if args.expected_pages is not None:
        expected = set(range(1, args.expected_pages + 1))
        observed = {item[0] for item in valid_records}
        for slide_no in sorted(expected - observed):
            add_issue(issues, "slide_missing_from_strip", slide_no=slide_no)
        for slide_no in sorted(observed - expected):
            add_issue(issues, "slide_outside_expected_range", slide_no=slide_no)
    valid_records.sort(key=lambda item: item[0])
    source_paths = {item[1] for item in valid_records}
    if output_path in source_paths:
        add_issue(issues, "output_conflicts_with_source_slide", path=str(output_path))
    if issues:
        result = {
            "schema": STRIP_SCHEMA,
            "valid": False,
            "technical_valid": False,
            "status": "blocked",
            "manifest_path": str(manifest_path),
            "output": str(output_path),
            "issues": issues,
        }
        if args.report:
            atomic_write_json(Path(args.report).resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 2

    if output_path.exists() and not args.force:
        add_issue(issues, "strip_exists", path=str(output_path))
    if args.record_in_manifest and isinstance(manifest.get("deck_strip"), dict) and not args.force:
        add_issue(issues, "manifest_deck_strip_exists")
    if issues:
        result = {"schema": STRIP_SCHEMA, "valid": False, "technical_valid": False, "status": "blocked", "manifest_path": str(manifest_path), "output": str(output_path), "issues": issues}
        if args.report:
            atomic_write_json(Path(args.report).resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 2

    try:
        sheet = make_sheet(
            [(slide_no, path, size) for slide_no, path, size, _record in valid_records],
            args.columns,
            args.padding,
            args.thumbnail_width,
        )
        atomic_replace(output_path, lambda path: sheet.save(str(path), format="PNG"), suffix=".tmp.visual-strip.png")
        output_hash = sha256(output_path)
        relative_output = output_path.relative_to(manifest_path.parent).as_posix()
        source_slides = [
            {"slide_no": slide_no, "image": record.get("copied_to"), "sha256": sha256(path)}
            for slide_no, path, _size, record in valid_records
        ]
        if args.record_in_manifest:
            updated_manifest = dict(manifest)
            updated_manifest["deck_strip"] = {
                "path": relative_output,
                "source_slides": source_slides,
                "columns": args.columns,
                "thumbnail_width": args.thumbnail_width,
                "sha256": output_hash,
                "generated_by": "scripts/build_visual_generation_strip.py",
                "review_status": "pending-human-review",
            }
            atomic_write_json(manifest_path, updated_manifest)
    except Exception as exc:
        issues.append({"severity": "blocker", "code": "strip_write_failed", "message": f"{type(exc).__name__}: {exc}"})

    valid = not issues
    result = {
        "schema": STRIP_SCHEMA,
        "valid": valid,
        "technical_valid": valid,
        "status": "passed" if valid else "blocked",
        "manifest_path": str(manifest_path),
        "output": str(output_path),
        "output_sha256": sha256(output_path) if output_path.is_file() else None,
        "slides": [{"slide_no": slide_no, "image": str(path), "size": list(size)} for slide_no, path, size, _record in valid_records],
        "recorded_in_manifest": bool(args.record_in_manifest and valid),
        "human_visual_review_required": True,
        "issues": issues,
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
