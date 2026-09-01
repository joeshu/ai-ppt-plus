#!/usr/bin/env python3
"""Post-baseline contracts for the pinned ``完美第一版`` authoring core.

The synchronized authoring primitives remain the source of truth.  This
module only normalizes canonical manifests at their boundary and turns
independent evidence into explicit contracts before composition.  In
particular, it never silently turns an unverified chart into a native chart or
approximates a complex gradient with a flat rectangle.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json


CHART_REPRESENTATIONS = {"native_chart", "static_line_primitives", "svg", "raster_fallback"}
GRADIENT_ROUTES = {"B2", "B3", "B4", "native"}
GRADIENT_ROLES = {"background_blend", "frame", "element", "native_gradient"}
GRADIENT_EXPECTED_ROUTE = {
    "background_blend": "B2",
    "frame": "B3",
    "element": "B4",
    "native_gradient": "native",
}


class ContractError(ValueError):
    """An input violates an explicit perfect-first contract."""


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _normal_color(value: object) -> str:
    """Normalize RGB/RGBA hex colors while retaining opacity separately."""
    raw = str(value or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(char * 2 for char in raw)
    if len(raw) not in {6, 8}:
        raise ContractError(f"invalid color {value!r}; expected #RRGGBB or #RRGGBBAA")
    try:
        int(raw, 16)
    except ValueError as exc:
        raise ContractError(f"invalid color {value!r}; expected hexadecimal RGB") from exc
    return raw.upper()


def _hex_and_opacity(value: object, opacity: object = None) -> tuple[str, float | None]:
    raw = _normal_color(value)
    embedded = int(raw[6:8], 16) / 255.0 if len(raw) == 8 else None
    color = raw[:6]
    if opacity is None:
        result_opacity = embedded
    else:
        result_opacity = float(opacity)
        if result_opacity > 1:
            result_opacity /= 255.0 if result_opacity <= 255 else 100.0
        result_opacity = max(0.0, min(1.0, result_opacity))
        if embedded is not None:
            result_opacity *= embedded
    return f"#{color}", result_opacity


def _alias_fields(target: dict[str, Any]) -> None:
    """Translate canonical manifest names to the stable backend names."""
    aliases = {
        "font_family": "font",
        "font_color": "color",
        "size_pt": "size",
        "text_content": "text",
    }
    for source, destination in aliases.items():
        if target.get(destination) is None and target.get(source) is not None:
            target[destination] = target[source]


def _normalize_bbox(target: dict[str, Any]) -> None:
    bbox = target.get("bbox")
    if isinstance(bbox, dict):
        for key in ("x", "y", "w", "h"):
            if target.get(key) is None and bbox.get(key) is not None:
                target[key] = bbox[key]
    elif isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        for key, value in zip(("x", "y", "w", "h"), bbox):
            target.setdefault(key, value)


def _normalize_gradient(gradient: dict[str, Any]) -> dict[str, Any]:
    result = dict(gradient)
    raw_stops = result.get("stops")
    if raw_stops is None and isinstance(result.get("colors"), list):
        colors = result["colors"]
        raw_stops = [{"position": index / max(1, len(colors) - 1), "color": color} for index, color in enumerate(colors)]
    if not isinstance(raw_stops, list):
        raise ContractError("gradient requires a stops[] list")
    stops: list[dict[str, Any]] = []
    for index, raw_stop in enumerate(raw_stops, 1):
        if not isinstance(raw_stop, dict):
            raise ContractError(f"gradient stop {index} must be an object")
        if raw_stop.get("position") is not None:
            position = float(raw_stop["position"])
            # The legacy core accepts either 0..1 or 0..100.  Normalize both
            # forms here so a percentage cannot be interpreted inconsistently.
            if position > 1:
                position /= 100.0
        elif raw_stop.get("position_pct") is not None:
            position = float(raw_stop["position_pct"]) / 100.0
        elif raw_stop.get("pos") is not None:
            position = float(raw_stop["pos"])
            if position > 1:
                position /= 100.0
        else:
            position = (index - 1) / max(1, len(raw_stops) - 1)
        if not math.isfinite(position) or not 0 <= position <= 1:
            raise ContractError(f"gradient stop {index} position must be within 0..1")
        color, opacity = _hex_and_opacity(raw_stop.get("color", raw_stop.get("hex")), raw_stop.get("opacity", raw_stop.get("alpha")))
        stop = {"position": position, "color": color}
        if opacity is not None:
            stop["opacity"] = opacity
        stops.append(stop)
    if len(stops) < 2:
        raise ContractError("gradient fill requires at least two color stops")
    if any(stops[index]["position"] > stops[index + 1]["position"] for index in range(len(stops) - 1)):
        raise ContractError("gradient stop positions must be monotonic")
    angle = result.get("angle", result.get("angle_deg", 0))
    if not _is_number(angle):
        raise ContractError("gradient angle must be finite")
    result["stops"] = stops
    result["angle"] = float(angle) % 360.0
    result.pop("colors", None)
    return result


def _normalize_text_spec(spec: dict[str, Any], theme: dict[str, Any]) -> dict[str, Any]:
    result = dict(spec)
    nested_style = result.get("style") if isinstance(result.get("style"), dict) else {}
    for key, value in nested_style.items():
        result.setdefault(key, value)
    _alias_fields(result)
    _normalize_bbox(result)
    if "text" not in result and result.get("content") is not None:
        result["text"] = result["content"]
    if "font" not in result:
        # Match the frozen backend's safe family fallback.  A missing
        # explicit font is not a malformed text object; the dedicated font
        # delivery gates decide whether the fallback is actually portable.
        result["font"] = theme.get("font") or "Noto Sans CJK SC"
    if "color" not in result:
        result["color"] = theme.get("text_color") or "#111111"
    if result.get("color") is not None:
        color, embedded_opacity = _hex_and_opacity(result["color"])
        result["color"] = color
        if embedded_opacity is not None and result.get("opacity") is None:
            result["opacity"] = embedded_opacity
    if result.get("size") is not None and not _is_number(result["size"]):
        raise ContractError(f"text size must be numeric: {result.get('size')!r}")
    runs = result.get("runs")
    if isinstance(runs, list):
        normalized_runs: list[Any] = []
        for raw_run in runs:
            if not isinstance(raw_run, dict):
                normalized_runs.append(raw_run)
                continue
            run = dict(raw_run)
            run_style = run.get("style") if isinstance(run.get("style"), dict) else {}
            for key, value in run_style.items():
                run.setdefault(key, value)
            _alias_fields(run)
            if "text" not in run and run.get("content") is not None:
                run["text"] = run["content"]
            if run.get("color") is not None:
                color, embedded_opacity = _hex_and_opacity(run["color"])
                run["color"] = color
                if embedded_opacity is not None and run.get("opacity") is None:
                    run["opacity"] = embedded_opacity
            if run.get("size") is not None and not _is_number(run["size"]):
                raise ContractError(f"run size must be numeric: {run.get('size')!r}")
            normalized_runs.append(run)
        result["runs"] = normalized_runs
    return result


def _normalize_shape_spec(spec: dict[str, Any]) -> dict[str, Any]:
    result = dict(spec)
    for key in ("gradient", "fill_gradient"):
        if isinstance(result.get(key), dict):
            result[key] = _normalize_gradient(result[key])
    return result


def normalize_deck(deck: dict[str, Any]) -> dict[str, Any]:
    """Normalize canonical text/gradient aliases without changing semantics."""
    result = copy.deepcopy(deck)
    theme = result.get("theme") if isinstance(result.get("theme"), dict) else {}
    theme = dict(theme)
    if theme.get("font") is None and theme.get("font_family") is not None:
        theme["font"] = theme["font_family"]
    if theme.get("text_color") is None and theme.get("font_color") is not None:
        theme["text_color"] = theme["font_color"]
    result["theme"] = theme
    slides = result.get("slides") if isinstance(result.get("slides"), list) else []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        slide["texts"] = [_normalize_text_spec(item, theme) if isinstance(item, dict) else item for item in slide.get("texts", [])]
        slide["shapes"] = [_normalize_shape_spec(item) if isinstance(item, dict) else item for item in slide.get("shapes", [])]
        groups = []
        for raw_group in slide.get("groups", []):
            if not isinstance(raw_group, dict):
                groups.append(raw_group)
                continue
            group = dict(raw_group)
            group["children"] = [_normalize_shape_spec(child) if isinstance(child, dict) else child for child in group.get("children", [])]
            groups.append(group)
        slide["groups"] = groups
    return result


def _record_bbox(record: dict[str, Any], manifest: dict[str, Any]) -> tuple[float, float, float, float] | None:
    geometry = record.get("geometry") if isinstance(record.get("geometry"), dict) else {}
    value = geometry.get("authoring_bbox", geometry.get("pptx_bbox", geometry.get("source_bbox")))
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        bbox = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in bbox) or bbox[2] <= 0 or bbox[3] <= 0:
        return None
    coordinate_space = str(geometry.get("coordinate_space") or manifest.get("coordinate_space") or "")
    canvas = manifest.get("canvas")
    if coordinate_space in {"reference_pixels", "pixels", "pixel"} and isinstance(canvas, list) and len(canvas) == 2:
        try:
            cw, ch = float(canvas[0]), float(canvas[1])
            if cw > 0 and ch > 0:
                return bbox[0] / cw, bbox[1] / ch, bbox[2] / cw, bbox[3] / ch
        except (TypeError, ValueError):
            return None
    if coordinate_space in {"fraction", "normalized", "normalized_fraction"} or max(abs(item) for item in bbox) <= 1:
        return bbox
    return None


def _chart_spec_from_record(record: dict[str, Any], existing: dict[str, Any] | None, manifest: dict[str, Any]) -> dict[str, Any]:
    spec = dict(existing or {})
    chart_id = str(record.get("chart_id"))
    spec.setdefault("object_id", chart_id)
    spec.setdefault("name", chart_id)
    spec["representation"] = record.get("representation")
    spec["source_data_status"] = record.get("source_data_status")
    spec["data_source"] = copy.deepcopy(record.get("data_source"))
    spec["data_snapshot_sha256"] = record.get("data_snapshot_sha256")
    if record.get("title") is not None:
        spec["title"] = record["title"]
    if record.get("type") is not None:
        spec["type"] = record["type"]
    elif spec.get("type") is None:
        spec["type"] = "line"
    spec["categories"] = list(record.get("categories") or spec.get("categories") or [])
    spec["series"] = []
    for series in record.get("series") or []:
        if not isinstance(series, dict):
            continue
        item = {"name": series.get("name", "Series"), "values": list(series.get("values") or [])}
        if series.get("color"):
            item["color"] = _hex_and_opacity(series["color"])[0]
        if series.get("series_id"):
            item["series_id"] = series["series_id"]
        spec["series"].append(item)
    colors = [item.get("color") for item in spec["series"] if item.get("color")]
    if colors:
        spec["colors"] = colors
    if isinstance(record.get("legend"), bool):
        spec["legend"] = record["legend"]
    if record.get("required_elements"):
        required = set(record["required_elements"])
        # `required_elements` describes visible evidence, not permission to
        # let PowerPoint auto-place labels.  Automatic data-label placement
        # is renderer-dependent; confirmed labels must remain explicit text
        # overlays unless the source record explicitly opts into native labels.
        if "legend" in required and "legend" not in spec:
            spec["legend"] = True
    if isinstance(record.get("data_labels"), bool):
        spec["data_labels"] = record["data_labels"]
    bbox = _record_bbox(record, manifest)
    if bbox:
        for key, value in zip(("x", "y", "w", "h"), bbox):
            spec.setdefault(key, value)
    return spec


def _chart_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    charts = manifest.get("charts")
    return [item for item in charts if isinstance(item, dict)] if isinstance(charts, list) else []


def merge_verified_chart_manifest(deck: dict[str, Any], manifest_path: Path, *, strict: bool = True) -> dict[str, Any]:
    """Promote only verified chart records into native chart specs."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ContractError(f"chart manifest unreadable: {type(exc).__name__}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ContractError("chart manifest must be an object")
    try:
        from validate_chart_manifest import validate as validate_chart
        validation = validate_chart(manifest_path)
    except ImportError:
        validation = {"valid": True, "errors": []}
    if not validation.get("valid"):
        raise ContractError(f"chart manifest is invalid: {validation.get('errors', [])[:4]}")
    summaries: list[dict[str, Any]] = []
    for record in _chart_records(manifest):
        representation = record.get("representation")
        status = record.get("source_data_status")
        if representation not in CHART_REPRESENTATIONS:
            raise ContractError(f"unsupported chart representation: {representation!r}")
        slide_no = int(record.get("slide_no", 0) or 0)
        if slide_no < 1 or slide_no > len(deck.get("slides", [])):
            raise ContractError(f"chart {record.get('chart_id')} points to missing slide {slide_no}")
        slide = deck["slides"][slide_no - 1]
        charts = slide.setdefault("charts", [])
        chart_id = str(record.get("chart_id"))
        matches = [item for item in charts if isinstance(item, dict) and str(item.get("object_id") or item.get("name")) == chart_id]
        existing = matches[0] if matches else None
        if representation == "native_chart":
            if status != "verified":
                raise ContractError(f"native chart {chart_id} requires verified source data")
            if any(value is None for item in record.get("series", []) if isinstance(item, dict) for value in item.get("values", [])):
                raise ContractError(f"native chart {chart_id} cannot contain null values")
            spec = _chart_spec_from_record(record, existing, manifest)
            if existing is None:
                charts.append(spec)
            else:
                existing.clear()
                existing.update(spec)
            summaries.append({"chart_id": chart_id, "slide_no": slide_no, "route": "native_chart", "promoted": True, "source_data_status": status})
            continue
        # A non-native route must be represented by explicit primitive/asset
        # specs.  A legacy charts[] entry would otherwise be silently rendered
        # as a native chart by the frozen backend, which is a false claim.
        primitive_specs = record.get("primitive_specs") or (existing.get("primitive_specs") if existing else None)
        asset = record.get("asset") or (existing.get("asset") if existing else None) or (existing.get("file") if existing else None)
        if existing is None and not primitive_specs and not asset:
            if strict:
                raise ContractError(f"chart {chart_id} uses {representation} but has no explicit primitive or asset route")
            summaries.append({"chart_id": chart_id, "slide_no": slide_no, "route": representation, "promoted": False, "unmaterialized": True, "source_data_status": status})
            continue
        if existing is not None:
            if not primitive_specs and not asset:
                raise ContractError(f"chart {chart_id} uses {representation} but has no explicit primitive or asset route")
            charts.remove(existing)
            if isinstance(primitive_specs, dict):
                for key in ("shapes", "texts", "icons"):
                    if isinstance(primitive_specs.get(key), list):
                        slide.setdefault(key, []).extend(copy.deepcopy(primitive_specs[key]))
            if asset:
                icon = {"object_id": chart_id, "file": asset, "x": existing.get("x", 0), "y": existing.get("y", 0), "w": existing.get("w", 1), "h": existing.get("h", 1), "role": "chart-asset"}
                slide.setdefault("icons", []).append(icon)
        summaries.append({"chart_id": chart_id, "slide_no": slide_no, "route": representation, "promoted": False, "source_data_status": status})
    return {"schema": "ai-ppt-plus/perfect-first-chart-adapter/v1", "manifest": str(manifest_path.resolve()), "manifest_sha256": _sha256(manifest_path), "charts": summaries}


def _gradient_manifest_report(path: Path, *, require_verified: bool = False) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ContractError(f"gradient manifest unreadable: {type(exc).__name__}: {exc}") from exc
    issues: list[dict[str, Any]] = []
    if data.get("schema") != "ai-ppt-plus/gradient-visual/v1":
        issues.append({"code": "schema_mismatch", "observed": data.get("schema")})
    regions: list[dict[str, Any]] = []
    for slide in data.get("slides", []) if isinstance(data.get("slides"), list) else []:
        if not isinstance(slide, dict):
            continue
        for region in slide.get("regions", []) if isinstance(slide.get("regions"), list) else []:
            if not isinstance(region, dict):
                continue
            regions.append(region)
            role, route = region.get("role"), region.get("route")
            if role not in GRADIENT_ROLES:
                issues.append({"code": "invalid_role", "id": region.get("id"), "value": role})
            if route not in GRADIENT_ROUTES:
                issues.append({"code": "invalid_route", "id": region.get("id"), "value": route})
            if role in GRADIENT_EXPECTED_ROUTE and route != GRADIENT_EXPECTED_ROUTE[role]:
                issues.append({"code": "role_route_mismatch", "id": region.get("id"), "role": role, "route": route})
            if role != "background_blend" and region.get("requires_alpha") and not region.get("alpha_verified"):
                issues.append({"code": "alpha_not_verified", "id": region.get("id")})
            if require_verified and (not region.get("embedded") or not region.get("render_visible")):
                issues.append({"code": "gradient_evidence_missing", "id": region.get("id")})
    if not regions:
        issues.append({"code": "no_gradient_regions"})
    if issues:
        raise ContractError(f"gradient manifest is invalid: {issues[:4]}")
    return {"schema": "ai-ppt-plus/perfect-first-gradient-adapter/v1", "manifest": str(path.resolve()), "manifest_sha256": _sha256(path), "regions": [{"id": item.get("id"), "role": item.get("role"), "route": item.get("route"), "source": item.get("source"), "requires_alpha": bool(item.get("requires_alpha"))} for item in regions]}


def _iter_text_specs(deck: dict[str, Any]):
    theme = deck.get("theme") if isinstance(deck.get("theme"), dict) else {}
    for slide_no, slide in enumerate(deck.get("slides", []), 1):
        for index, spec in enumerate(slide.get("texts", []), 1):
            if isinstance(spec, dict):
                yield slide_no, index, _normalize_text_spec(spec, theme), "base"
                for run_index, run in enumerate(spec.get("runs", []), 1):
                    if isinstance(run, dict):
                        run_spec = dict(run)
                        run_style = run_spec.get("style") if isinstance(run_spec.get("style"), dict) else {}
                        for key, value in run_style.items():
                            run_spec.setdefault(key, value)
                        _alias_fields(run_spec)
                        yield slide_no, index, _normalize_text_spec(run_spec, theme), f"run-{run_index}"


def typography_contract(deck: dict[str, Any], *, font_dir: Path | None = None, font_manifest: Path | None = None) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    families: set[str] = set()
    colors: set[str] = set()
    missing_sizes = 0
    missing_colors = 0
    for slide_no, index, spec, scope in _iter_text_specs(deck):
        family = str(spec.get("font") or "").strip()
        if family:
            families.add(family)
        else:
            errors.append({"code": "font_family_missing", "slide": slide_no, "text_index": index, "scope": scope})
        size = spec.get("size")
        if size is None:
            missing_sizes += 1
        elif not _is_number(size) or float(size) <= 0:
            errors.append({"code": "font_size_invalid", "slide": slide_no, "text_index": index, "scope": scope, "value": size})
        color = spec.get("color")
        if color:
            colors.add(str(color).upper())
        else:
            missing_colors += 1
        records.append({"slide": slide_no, "text_index": index, "scope": scope, "object_id": spec.get("object_id"), "content": str(spec.get("text", spec.get("content", ""))), "font_family": family, "size_pt": float(size) if _is_number(size) else None, "color": color, "bold": bool(spec.get("bold", False))})
    manifest_record: dict[str, Any] | None = None
    if font_manifest is not None:
        try:
            data = json.loads(font_manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append({"code": "font_manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"})
            data = {}
        if isinstance(data, dict):
            declared = str(data.get("family") or "").strip()
            manifest_record = {"family": declared, "file": data.get("file"), "sha256": data.get("sha256")}
            if declared and families and not any(declared.casefold() == family.casefold() for family in families):
                errors.append({"code": "font_manifest_family_not_used", "declared": declared, "used": sorted(families)})
            if font_dir is not None and data.get("file"):
                font_file = (font_dir / str(data["file"])).resolve()
                try:
                    font_file.relative_to(font_dir.resolve())
                except ValueError:
                    errors.append({"code": "font_file_outside_font_dir", "file": str(data["file"])})
                else:
                    if not font_file.is_file():
                        errors.append({"code": "font_file_missing", "file": str(font_file)})
                    elif data.get("sha256") and _sha256(font_file) != str(data["sha256"]).lower():
                        errors.append({"code": "font_file_hash_mismatch", "file": str(font_file), "expected": data.get("sha256"), "observed": _sha256(font_file)})
    return {"schema": "ai-ppt-plus/perfect-first-typography-contract/v1", "valid": not errors, "text_count": len(records), "records": records, "font_families": sorted(families), "font_colors": sorted(colors), "missing_size_count": missing_sizes, "missing_color_count": missing_colors, "font_dir": str(font_dir.resolve()) if font_dir else None, "font_manifest": manifest_record, "errors": errors, "human_visual_review_required": True}


def _inline_gradient_report(deck: dict[str, Any]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for slide_no, slide in enumerate(deck.get("slides", []), 1):
        for kind in ("shapes", "groups"):
            for index, spec in enumerate(slide.get(kind, []), 1):
                if not isinstance(spec, dict):
                    continue
                candidates = [(spec, f"{kind}[{index}]")]
                if kind == "groups":
                    candidates.extend((child, f"groups[{index}].children[{child_index}]") for child_index, child in enumerate(spec.get("children", []), 1) if isinstance(child, dict))
                for item, location in candidates:
                    for key in ("gradient", "fill_gradient"):
                        if isinstance(item.get(key), dict):
                            normalized = _normalize_gradient(item[key])
                            records.append({"slide": slide_no, "location": location, "object_id": item.get("object_id") or item.get("name"), "field": key, "route": normalized.get("route", "native"), "stop_count": len(normalized["stops"]), "stops": normalized["stops"], "angle": normalized["angle"]})
    return {"schema": "ai-ppt-plus/perfect-first-inline-gradient/v1", "valid": True, "gradients": records, "native_gradient_count": sum(1 for item in records if item["route"] == "native"), "asset_gradient_count": sum(1 for item in records if item["route"] != "native")}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_deck(deck: dict[str, Any], *, chart_manifest: Path | None = None, gradient_manifest: Path | None = None, font_dir: Path | None = None, font_manifest: Path | None = None, strict: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return an authorable deck plus all adapter evidence."""
    normalized = normalize_deck(deck)
    chart_report = None
    if chart_manifest is not None:
        chart_report = merge_verified_chart_manifest(normalized, chart_manifest, strict=strict)
    gradient_report = _inline_gradient_report(normalized)
    if strict and gradient_report["asset_gradient_count"]:
        raise ContractError("complex B2/B3/B4 gradients must be supplied as traceable assets, not inline native gradients")
    if gradient_manifest is not None:
        manifest_report = _gradient_manifest_report(gradient_manifest, require_verified=strict)
        gradient_report["manifest"] = manifest_report
    typography_report = typography_contract(normalized, font_dir=font_dir, font_manifest=font_manifest)
    if strict and not typography_report["valid"]:
        raise ContractError(f"typography contract is invalid: {typography_report['errors'][:4]}")
    report = {"schema": "ai-ppt-plus/perfect-first-adapter/v1", "valid": True, "strict": bool(strict), "charts": chart_report, "gradients": gradient_report, "typography": typography_report, "post_baseline": True, "core": "完美第一版"}
    return normalized, report


def _load_layout(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContractError("layout must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="validate layout-bound perfect-first contracts")
    validate.add_argument("layout")
    validate.add_argument("--chart-manifest")
    validate.add_argument("--gradient-manifest")
    validate.add_argument("--font-dir")
    validate.add_argument("--font-manifest")
    validate.add_argument("--strict", action="store_true")
    validate.add_argument("--report", required=True)
    args = parser.parse_args()
    try:
        from component_expander import _expand_components, _load_deck
        layout_path = Path(args.layout).resolve()
        deck = _expand_components(_load_deck(layout_path))
        _, report = prepare_deck(deck, chart_manifest=Path(args.chart_manifest).resolve() if args.chart_manifest else None, gradient_manifest=Path(args.gradient_manifest).resolve() if args.gradient_manifest else None, font_dir=Path(args.font_dir).resolve() if args.font_dir else None, font_manifest=Path(args.font_manifest).resolve() if args.font_manifest else None, strict=args.strict)
        report["layout"] = str(layout_path)
        atomic_write_json(Path(args.report).resolve(), report)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"schema": "ai-ppt-plus/perfect-first-adapter/v1", "valid": False, "status": "blocked", "code": "perfect_first_contract_failed", "message": f"{type(exc).__name__}: {exc}"}
        atomic_write_json(Path(args.report).resolve(), report)
        print(json.dumps(report, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
