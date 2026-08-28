#!/usr/bin/env python3
"""Canonical TextSpec/TextRunSpec builder and validator.

The module is deliberately stdlib-only so it can be used by the pipeline and
by external agents without an additional dependency.  Raw ``layout.json``
text records remain accepted as an input compatibility format.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA = "ai-ppt-plus/text-layout-manifest/v1"
VALIDATION_SCHEMA = "ai-ppt-plus/text-layout-validation/v1"
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$")
ALIGNMENTS = {"left", "center", "right", "justify"}
VALIGNS = {"top", "middle", "center", "bottom"}
STYLE_KEYS = (
    "font", "font_family", "size", "size_pt", "size_px", "size_ratio", "size_pct",
    "color", "bold", "italic", "opacity", "line_spacing", "align", "valign",
    "margin_left", "margin_right", "margin_top", "margin_bottom",
)


def _number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _box(item: dict[str, Any]) -> dict[str, float] | None:
    values = [_number(item.get(key)) for key in ("x", "y", "w", "h")]
    if any(value is None for value in values):
        return None
    return dict(zip(("x", "y", "w", "h"), (float(value) for value in values)))


def _source_bbox(item: dict[str, Any]) -> list[float] | None:
    value = item.get("source_bbox")
    if not isinstance(value, list) or len(value) != 4:
        return None
    numbers = [_number(part) for part in value]
    if any(part is None for part in numbers):
        return None
    return [float(part) for part in numbers]


def _style(item: dict[str, Any], *, run: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in STYLE_KEYS:
        if key in item and item[key] is not None:
            result[key] = item[key]
    if "font" in result and "font_family" not in result:
        result["font_family"] = result["font"]
    if "font_family" in result and "font" not in result:
        result["font"] = result["font_family"]
    if run:
        result.pop("font_family", None)
        result.pop("font", None) if "font" not in item else None
    return result


def normalize_text_spec(item: dict[str, Any], slide_no: int, index: int, *, units: str = "fraction", ref_width: Any = None, ref_height: Any = None) -> dict[str, Any]:
    """Normalize one raw layout text record without inventing its content."""
    text_id = str(item.get("text_id") or item.get("object_id") or item.get("name") or f"text-{index:02d}")
    raw_runs = item.get("runs")
    runs = []
    runs_input_valid = "runs" not in item or isinstance(raw_runs, list)
    if isinstance(raw_runs, list):
        for run_index, raw in enumerate(raw_runs, 1):
            if not isinstance(raw, dict):
                runs.append({"run_id": f"{text_id}.r{run_index:02d}", "text": raw})
                continue
            record = {
                "run_id": str(raw.get("run_id") or f"{text_id}.r{run_index:02d}"),
                "text": str(raw.get("text", "")),
            }
            style = _style(raw, run=True)
            if style:
                record["style"] = style
            if raw.get("literal_redaction") is True:
                record["literal_redaction"] = True
            runs.append(record)
    content = "".join(str(run.get("text", "")) for run in runs) if isinstance(raw_runs, list) else str(item.get("text", ""))
    spec: dict[str, Any] = {
        "text_id": text_id,
        "slide_no": slide_no,
        "content": content,
        "source_ref": item.get("source_ref") or item.get("provenance"),
        "source_bbox": _source_bbox(item),
        "coordinate_space": units,
        "bbox": _box(item),
        "style": _style(item),
        "runs": runs,
        "runs_input_valid": runs_input_valid,
        "literal_redaction": bool(item.get("literal_redaction")) or any(run.get("literal_redaction") is True for run in runs),
        "emphasis_expected": bool(item.get("emphasis_expected")),
        "wrap": {
            "word_wrap": item.get("word_wrap", True),
            "preserve_line_breaks": item.get("preserve_line_breaks", True),
        },
        "source_index": index,
    }
    if ref_width is not None or ref_height is not None:
        spec["reference_size"] = {"width": ref_width, "height": ref_height}
    spec = {
        key: value for key, value in spec.items()
        if value is not None and value != {} and (value != [] or key == "runs")
    }
    if not runs and "text" in item and item.get("text") is not None:
        spec["raw_text_present"] = True
    if "text" in item and isinstance(item.get("text"), (str, int, float)):
        spec["declared_text"] = str(item["text"])
    return spec


def _layout_slides(data: dict[str, Any]) -> list[dict[str, Any]]:
    slides = data.get("slides")
    if isinstance(slides, list):
        return [slide for slide in slides if isinstance(slide, dict)]
    return [{key: data[key] for key in ("texts",) if key in data}]


def build_manifest(layout: dict[str, Any]) -> dict[str, Any]:
    units = str(layout.get("units", "fraction"))
    ref_width, ref_height = layout.get("ref_width"), layout.get("ref_height")
    slides = []
    for slide_index, slide in enumerate(_layout_slides(layout), 1):
        slide_no = int(slide.get("slide_no", slide_index))
        specs = [
            normalize_text_spec(item, slide_no, index, units=units, ref_width=ref_width, ref_height=ref_height)
            for index, item in enumerate(slide.get("texts", []), 1)
            if isinstance(item, dict)
        ]
        slides.append({"slide_no": slide_no, "text_specs": specs})
    return {
        "schema": SCHEMA,
        "project_id": layout.get("project_id", ""),
        "layout_ref": "layout.json",
        "units": units,
        "reference_size": {"width": ref_width, "height": ref_height},
        "slides": slides,
    }


def _valid_number(value: Any) -> bool:
    return _number(value) is not None


def _validate_style(style: Any, label: str, issues: list[dict[str, Any]], warnings: list[dict[str, Any]], required: bool = False) -> None:
    if not isinstance(style, dict):
        if required:
            warnings.append({"code": "text_style_missing", "text_id": label})
        return
    font = style.get("font_family", style.get("font"))
    if required and (not isinstance(font, str) or not font.strip()):
        warnings.append({"code": "text_font_missing", "text_id": label})
    sizes = [style.get(key) for key in ("size", "size_pt", "size_px", "size_ratio", "size_pct") if style.get(key) is not None]
    if required and not sizes:
        warnings.append({"code": "text_size_missing", "text_id": label})
    if any(not _valid_number(value) or float(value) <= 0 for value in sizes):
        issues.append({"code": "text_size_invalid", "text_id": label})
    if style.get("color") is not None and (not isinstance(style["color"], str) or not HEX_COLOR.fullmatch(style["color"])):
        issues.append({"code": "text_color_invalid", "text_id": label, "value": style.get("color")})
    if style.get("align") is not None and style["align"] not in ALIGNMENTS:
        issues.append({"code": "text_alignment_invalid", "text_id": label, "value": style["align"]})
    if style.get("valign") is not None and style["valign"] not in VALIGNS:
        issues.append({"code": "text_vertical_alignment_invalid", "text_id": label, "value": style["valign"]})
    for key in ("line_spacing", "margin_left", "margin_right", "margin_top", "margin_bottom", "opacity"):
        if style.get(key) is not None and (not _valid_number(style[key]) or float(style[key]) < 0 or (key == "opacity" and float(style[key]) > 1)):
            issues.append({"code": "text_style_number_invalid", "text_id": label, "field": key})


def validate_manifest(data: dict[str, Any], *, strict: bool = False, require_source_bbox: bool = False) -> dict[str, Any]:
    canonical = data if data.get("schema") == SCHEMA else build_manifest(data)
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()
    text_count = 0
    run_count = 0
    slides = canonical.get("slides", []) if isinstance(canonical.get("slides"), list) else []
    units = canonical.get("units", "fraction")
    ref_size = canonical.get("reference_size") or {}
    for slide_index, slide in enumerate(slides, 1):
        specs = slide.get("text_specs", []) if isinstance(slide, dict) else []
        if not isinstance(specs, list):
            issues.append({"code": "text_specs_not_array", "slide_no": slide.get("slide_no") if isinstance(slide, dict) else slide_index})
            continue
        for index, spec in enumerate(specs, 1):
            text_count += 1
            if not isinstance(spec, dict):
                issues.append({"code": "text_spec_not_object", "slide_no": slide_index, "index": index})
                continue
            text_id = spec.get("text_id")
            label = str(text_id or f"S{slide_index}.T{index}")
            if not isinstance(text_id, str) or not text_id.strip():
                issues.append({"code": "text_id_missing", "slide_no": slide_index, "index": index})
            elif text_id in seen:
                issues.append({"code": "text_id_duplicate", "text_id": text_id})
            else:
                seen.add(text_id)
            content = spec.get("content")
            if not isinstance(content, str):
                issues.append({"code": "text_content_not_string", "text_id": label})
                content = ""
            if not content.strip():
                warnings.append({"code": "text_content_empty", "text_id": label})
            if spec.get("declared_text") is not None and spec.get("declared_text") != content:
                issues.append({"code": "declared_text_content_mismatch", "text_id": label})
            if "**" in content and spec.get("literal_redaction") is not True:
                issues.append({"code": "visible_redaction_marker_without_declaration", "text_id": label})
            bbox = spec.get("bbox")
            if bbox is None:
                warnings.append({"code": "text_bbox_missing", "text_id": label})
            elif not isinstance(bbox, dict) or any(not _valid_number(bbox.get(key)) for key in ("x", "y", "w", "h")):
                issues.append({"code": "text_bbox_invalid", "text_id": label})
            elif float(bbox["w"]) <= 0 or float(bbox["h"]) <= 0:
                issues.append({"code": "text_bbox_non_positive", "text_id": label})
            elif units == "fraction" and (any(float(bbox[key]) < 0 or float(bbox[key]) > 1 for key in ("x", "y", "w", "h")) or float(bbox["x"]) + float(bbox["w"]) > 1 or float(bbox["y"]) + float(bbox["h"]) > 1):
                warnings.append({"code": "text_bbox_fraction_outside_unit", "text_id": label})
            source_bbox = spec.get("source_bbox")
            if require_source_bbox and source_bbox is None:
                warnings.append({"code": "text_source_bbox_missing", "text_id": label})
            if source_bbox is not None:
                if not isinstance(source_bbox, list) or len(source_bbox) != 4 or any(not _valid_number(value) for value in source_bbox):
                    issues.append({"code": "text_source_bbox_invalid", "text_id": label})
                elif source_bbox[2] <= 0 or source_bbox[3] <= 0:
                    issues.append({"code": "text_source_bbox_non_positive", "text_id": label})
                elif _valid_number(ref_size.get("width")) and _valid_number(ref_size.get("height")):
                    if source_bbox[0] < 0 or source_bbox[1] < 0 or source_bbox[0] + source_bbox[2] > ref_size["width"] or source_bbox[1] + source_bbox[3] > ref_size["height"]:
                        issues.append({"code": "text_source_bbox_out_of_bounds", "text_id": label})
            _validate_style(spec.get("style"), label, issues, warnings, required=bool(content.strip()))
            runs = spec.get("runs", [])
            if spec.get("runs_input_valid") is False:
                issues.append({"code": "text_runs_not_array", "text_id": label})
            if not isinstance(runs, list):
                issues.append({"code": "text_runs_not_array", "text_id": label})
                runs = []
            run_text = []
            run_ids = set()
            for run_index, run in enumerate(runs, 1):
                run_count += 1
                if not isinstance(run, dict):
                    issues.append({"code": "text_run_not_object", "text_id": label, "run_index": run_index})
                    continue
                run_id = run.get("run_id")
                if not isinstance(run_id, str) or not run_id.strip() or run_id in run_ids:
                    issues.append({"code": "text_run_id_invalid", "text_id": label, "run_index": run_index})
                run_ids.add(run_id)
                run_value = run.get("text")
                if not isinstance(run_value, str):
                    issues.append({"code": "text_run_text_not_string", "text_id": label, "run_index": run_index})
                    run_value = ""
                run_text.append(run_value)
                _validate_style(run.get("style", {}), f"{label}:{run_id}", issues, warnings)
            if runs and "".join(run_text) != content:
                issues.append({"code": "text_runs_content_mismatch", "text_id": label})
            if spec.get("emphasis_expected") is True and not runs:
                warnings.append({"code": "emphasis_runs_missing", "text_id": label})
    result = {
        "schema": VALIDATION_SCHEMA,
        "valid": not issues and not (strict and warnings),
        "status": "passed" if not issues and not (strict and warnings) else "blocked",
        "strict": strict,
        "text_count": text_count,
        "run_count": run_count,
        "issues": issues,
        "warnings": warnings,
        "slides": len(slides),
        "text_manifest_schema": canonical.get("schema"),
    }
    return result


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("layout")
    build_parser.add_argument("--output", required=True)
    build_parser.set_defaults(command_func="build")
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("input")
    validate_parser.add_argument("--report")
    validate_parser.add_argument("--strict", action="store_true")
    validate_parser.add_argument("--require-source-bbox", action="store_true")
    validate_parser.set_defaults(command_func="validate")
    args = parser.parse_args()
    source = Path(args.layout if args.command_func == "build" else args.input)
    try:
        data = _read(source)
        if args.command_func == "build":
            result = build_manifest(data)
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"schema": SCHEMA, "valid": True, "slides": len(result["slides"]), "text_count": sum(len(slide["text_specs"]) for slide in result["slides"]), "output": str(output)}, ensure_ascii=False))
            return 0
        result = validate_manifest(data, strict=args.strict, require_source_bbox=args.require_source_bbox)
        result["input"] = str(source.resolve())
        result["content_manifest_sha256"] = _digest(data)
        if args.report:
            report = Path(args.report)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["valid"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": VALIDATION_SCHEMA, "valid": False, "issues": [{"code": "input_error", "message": f"{type(exc).__name__}: {exc}"}]}, ensure_ascii=False))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
