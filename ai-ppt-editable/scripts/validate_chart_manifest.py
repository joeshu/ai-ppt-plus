#!/usr/bin/env python3
"""Validate traceable chart data and reference-image chart annotations."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/chart-reconstruction/v1"
REPRESENTATIONS = {"native_chart", "static_line_primitives", "svg", "raster_fallback"}
SOURCE_STATUSES = {"verified", "unverified", "unavailable"}
EDITABILITY_LEVELS = {"L0", "L1", "L2", "L3", "L4", "L5"}
ELEMENT_NAMES = {"title", "legend", "category_labels", "axis_labels", "data_labels", "units", "axis_titles"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("manifest must be a JSON object")
    return value


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_snapshot(chart: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "category_chart",
        "categories": list(chart.get("categories") or []),
        "series": [
            {
                "series_id": item.get("series_id"),
                "name": item.get("name"),
                "values": list(item.get("values") or []),
            }
            for item in (chart.get("series") or [])
            if isinstance(item, dict)
        ],
    }


def _digest_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _box(value: Any, *, canvas: tuple[float, float] | None = None) -> bool:
    if not isinstance(value, list) or len(value) != 4:
        return False
    try:
        x, y, w, h = (float(item) for item in value)
    except (TypeError, ValueError):
        return False
    if not all(math.isfinite(item) for item in (x, y, w, h)) or w <= 0 or h <= 0 or x < 0 or y < 0:
        return False
    if canvas and (x + w > canvas[0] or y + h > canvas[1]):
        return False
    return True


def _item_content(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    return str(item.get("content", item.get("text", "")) or "").strip()


def validate(
    path: Path,
    *,
    require_source: bool = False,
    content_inventory_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    try:
        manifest = _read(path)
    except Exception as exc:
        return {
            "schema": "ai-ppt-plus/chart-manifest-validation/v1",
            "valid": False,
            "status": "invalid",
            "manifest": str(path.resolve()),
            "errors": [{"severity": "blocker", "code": "runtime_error", "message": f"{type(exc).__name__}: {exc}"}],
            "warnings": [],
        }

    if manifest.get("schema") != SCHEMA:
        errors.append({"severity": "blocker", "code": "schema_invalid", "observed": manifest.get("schema")})
    if not isinstance(manifest.get("project_id"), str) or not manifest.get("project_id", "").strip():
        errors.append({"severity": "blocker", "code": "project_id_missing"})
    charts = manifest.get("charts")
    if not isinstance(charts, list) or not charts:
        errors.append({"severity": "blocker", "code": "charts_missing"})
        charts = []

    canvas_raw = manifest.get("canvas")
    canvas: tuple[float, float] | None = None
    if canvas_raw is not None:
        if not isinstance(canvas_raw, list) or len(canvas_raw) != 2:
            errors.append({"severity": "blocker", "code": "canvas_invalid"})
        else:
            try:
                canvas = (float(canvas_raw[0]), float(canvas_raw[1]))
                if min(canvas) <= 0 or not all(math.isfinite(item) for item in canvas):
                    raise ValueError
            except (TypeError, ValueError):
                errors.append({"severity": "blocker", "code": "canvas_invalid"})

    source_reference = manifest.get("source_reference")
    source_hash = manifest.get("source_sha256")
    if require_source and (not isinstance(source_reference, str) or not source_reference.strip()):
        errors.append({"severity": "blocker", "code": "source_reference_missing"})
    if source_reference:
        if not isinstance(source_reference, str):
            errors.append({"severity": "blocker", "code": "source_reference_invalid"})
        elif not isinstance(source_hash, str) or not SHA256_RE.fullmatch(source_hash):
            errors.append({"severity": "blocker", "code": "source_hash_missing_or_invalid"})
        else:
            source_path = (path.parent / source_reference).resolve()
            if source_path.is_file():
                observed = _digest_file(source_path)
                if observed != source_hash:
                    errors.append({"severity": "blocker", "code": "source_hash_mismatch", "expected": source_hash, "observed": observed})
            elif require_source:
                errors.append({"severity": "blocker", "code": "source_reference_missing", "path": str(source_path)})
            else:
                warnings.append({"severity": "major", "code": "source_reference_not_local", "path": str(source_path)})

    expected_chart_records: dict[tuple[int, str], dict[str, Any]] = {}
    if content_inventory_path is not None:
        try:
            inventory = _read(content_inventory_path)
            for slide in inventory.get("slides", []):
                if not isinstance(slide, dict):
                    continue
                try:
                    inventory_slide_no = int(slide.get("slide_no"))
                except (TypeError, ValueError):
                    continue
                for item in slide.get("charts", []):
                    if not isinstance(item, dict) or not isinstance(item.get("chart_id"), str):
                        continue
                    expected_chart_records[(inventory_slide_no, item["chart_id"])] = item
        except Exception as exc:
            errors.append({"severity": "blocker", "code": "content_inventory_runtime_error", "message": f"{type(exc).__name__}: {exc}"})

    seen_ids: set[str] = set()
    chart_summaries: list[dict[str, Any]] = []
    for index, chart in enumerate(charts, 1):
        prefix = f"charts[{index}]"
        if not isinstance(chart, dict):
            errors.append({"severity": "blocker", "code": "chart_not_object", "path": prefix})
            continue
        chart_id = chart.get("chart_id")
        if not isinstance(chart_id, str) or not chart_id.strip():
            errors.append({"severity": "blocker", "code": "chart_id_missing", "path": prefix})
            chart_id = f"index-{index}"
        elif chart_id in seen_ids:
            errors.append({"severity": "blocker", "code": "chart_id_duplicate", "chart_id": chart_id})
        seen_ids.add(chart_id)
        try:
            slide_no = int(chart.get("slide_no"))
            if slide_no < 1:
                raise ValueError
        except (TypeError, ValueError):
            errors.append({"severity": "blocker", "code": "slide_no_invalid", "chart_id": chart_id})
            slide_no = 0

        representation = chart.get("representation")
        source_status = chart.get("source_data_status")
        if representation not in REPRESENTATIONS:
            errors.append({"severity": "blocker", "code": "representation_invalid", "chart_id": chart_id, "observed": representation})
        if source_status not in SOURCE_STATUSES:
            errors.append({"severity": "blocker", "code": "source_data_status_invalid", "chart_id": chart_id, "observed": source_status})
        if representation == "native_chart" and source_status != "verified":
            errors.append({"severity": "blocker", "code": "native_chart_requires_verified_data", "chart_id": chart_id, "source_data_status": source_status})
        if representation == "raster_fallback" and not str(chart.get("degradation_reason") or chart.get("source_data_note") or "").strip():
            errors.append({"severity": "blocker", "code": "raster_degradation_reason_missing", "chart_id": chart_id})

        level = chart.get("editability_level")
        if level not in EDITABILITY_LEVELS:
            errors.append({"severity": "blocker", "code": "editability_level_invalid", "chart_id": chart_id, "observed": level})
        if representation == "raster_fallback" and level not in {"L3", "L4"}:
            errors.append({"severity": "blocker", "code": "raster_editability_level_invalid", "chart_id": chart_id, "observed": level})

        categories = chart.get("categories")
        if not isinstance(categories, list) or not categories or any(not isinstance(item, str) or not item.strip() for item in categories):
            errors.append({"severity": "blocker", "code": "categories_invalid", "chart_id": chart_id})
            categories = []
        if len(set(categories)) != len(categories):
            errors.append({"severity": "blocker", "code": "categories_duplicate", "chart_id": chart_id})

        series = chart.get("series")
        if not isinstance(series, list) or not series:
            errors.append({"severity": "blocker", "code": "series_missing", "chart_id": chart_id})
            series = []
        series_ids: set[str] = set()
        null_count = 0
        for series_index, item in enumerate(series, 1):
            if not isinstance(item, dict):
                errors.append({"severity": "blocker", "code": "series_not_object", "chart_id": chart_id, "index": series_index})
                continue
            series_id = item.get("series_id")
            if not isinstance(series_id, str) or not series_id.strip() or series_id in series_ids:
                errors.append({"severity": "blocker", "code": "series_id_invalid_or_duplicate", "chart_id": chart_id, "index": series_index})
            series_ids.add(str(series_id))
            if not isinstance(item.get("name"), str) or not item.get("name", "").strip():
                errors.append({"severity": "blocker", "code": "series_name_missing", "chart_id": chart_id, "series_id": series_id})
            values = item.get("values")
            if not isinstance(values, list) or len(values) != len(categories):
                errors.append({"severity": "blocker", "code": "series_length_mismatch", "chart_id": chart_id, "series_id": series_id, "expected": len(categories), "observed": len(values) if isinstance(values, list) else None})
                values = values if isinstance(values, list) else []
            for value_index, value in enumerate(values):
                if value is None:
                    null_count += 1
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    errors.append({"severity": "blocker", "code": "series_value_invalid", "chart_id": chart_id, "series_id": series_id, "category_index": value_index, "observed": value})
            labels = item.get("value_labels", [])
            if labels is not None and not isinstance(labels, list):
                errors.append({"severity": "blocker", "code": "value_labels_invalid", "chart_id": chart_id, "series_id": series_id})
            for label_index, label in enumerate(labels if isinstance(labels, list) else [], 1):
                if not isinstance(label, dict) or not _item_content(label):
                    errors.append({"severity": "blocker", "code": "value_label_invalid", "chart_id": chart_id, "series_id": series_id, "index": label_index})
                elif "category_index" in label:
                    try:
                        category_index = int(label["category_index"])
                        if category_index < 0 or category_index >= len(categories):
                            raise ValueError
                    except (TypeError, ValueError):
                        errors.append({"severity": "blocker", "code": "value_label_category_invalid", "chart_id": chart_id, "series_id": series_id, "index": label_index})
        if null_count and chart.get("missing_value_policy") != "blank_not_zero":
            errors.append({"severity": "blocker", "code": "missing_value_policy_invalid", "chart_id": chart_id, "null_values": null_count, "observed": chart.get("missing_value_policy")})

        data_source = chart.get("data_source")
        if representation in {"native_chart", "static_line_primitives"}:
            if not isinstance(data_source, dict) or not str(data_source.get("kind") or "").strip() or not str(data_source.get("method") or "").strip():
                errors.append({"severity": "blocker", "code": "data_source_evidence_missing", "chart_id": chart_id})
        snapshot = _canonical_snapshot(chart)
        observed_digest = _digest_json(snapshot)
        declared_digest = chart.get("data_snapshot_sha256")
        if not isinstance(declared_digest, str) or not SHA256_RE.fullmatch(declared_digest):
            errors.append({"severity": "blocker", "code": "data_snapshot_hash_missing_or_invalid", "chart_id": chart_id})
        elif declared_digest != observed_digest:
            errors.append({"severity": "blocker", "code": "data_snapshot_hash_mismatch", "chart_id": chart_id, "expected": declared_digest, "observed": observed_digest})

        required = chart.get("required_elements")
        visible = chart.get("visible_elements")
        if not isinstance(required, list) or not required:
            errors.append({"severity": "blocker", "code": "required_elements_missing", "chart_id": chart_id})
            required = []
        for element in required:
            if element not in ELEMENT_NAMES:
                errors.append({"severity": "blocker", "code": "required_element_invalid", "chart_id": chart_id, "element": element})
            elif not isinstance(visible, dict) or not isinstance(visible.get(element), list) or not visible.get(element):
                errors.append({"severity": "blocker", "code": "visible_element_missing", "chart_id": chart_id, "element": element})
            else:
                for item_index, item in enumerate(visible[element], 1):
                    if not isinstance(item, dict) or not _item_content(item):
                        errors.append({"severity": "blocker", "code": "visible_element_invalid", "chart_id": chart_id, "element": element, "index": item_index})

        geometry = chart.get("geometry")
        if not isinstance(geometry, dict):
            errors.append({"severity": "blocker", "code": "geometry_missing", "chart_id": chart_id})
        else:
            for name in ("source_bbox", "plot_bbox"):
                if not _box(geometry.get(name), canvas=canvas):
                    errors.append({"severity": "blocker", "code": "geometry_box_invalid", "chart_id": chart_id, "box": name})
            try:
                tolerance = float(geometry.get("point_anchor_tolerance"))
                if not math.isfinite(tolerance) or tolerance <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append({"severity": "blocker", "code": "point_anchor_tolerance_invalid", "chart_id": chart_id})

        qa = chart.get("qa")
        if not isinstance(qa, dict) or not _box(qa.get("reference_region"), canvas=canvas):
            errors.append({"severity": "blocker", "code": "qa_reference_region_invalid", "chart_id": chart_id})

        chart_summaries.append({
            "chart_id": chart_id,
            "slide_no": slide_no,
            "representation": representation,
            "source_data_status": source_status,
            "categories": len(categories),
            "series": len(series),
            "null_values": null_count,
            "data_snapshot_sha256": observed_digest,
        })

    if content_inventory_path is not None:
        observed_chart_keys = {(item["slide_no"], item["chart_id"]) for item in chart_summaries}
        for key, expected in expected_chart_records.items():
            if key not in observed_chart_keys:
                errors.append({"severity": "blocker", "code": "chart_manifest_missing_chart", "slide_no": key[0], "chart_id": key[1]})
        for item in chart_summaries:
            key = (item["slide_no"], item["chart_id"])
            expected = expected_chart_records.get(key)
            if expected is None:
                errors.append({"severity": "blocker", "code": "chart_manifest_unexpected_chart", "slide_no": key[0], "chart_id": key[1]})
                continue
            expected_representation = expected.get("representation")
            if expected_representation and item["representation"] != expected_representation:
                errors.append({
                    "severity": "blocker",
                    "code": "chart_representation_mismatch",
                    "slide_no": key[0],
                    "chart_id": key[1],
                    "inventory": expected_representation,
                    "manifest": item["representation"],
                })
            expected_status = expected.get("source_data_status")
            if expected_status and item["source_data_status"] != expected_status:
                errors.append({
                    "severity": "blocker",
                    "code": "chart_source_status_mismatch",
                    "slide_no": key[0],
                    "chart_id": key[1],
                    "inventory": expected_status,
                    "manifest": item["source_data_status"],
                })

    result = {
        "schema": "ai-ppt-plus/chart-manifest-validation/v1",
        "valid": not errors,
        "status": "passed" if not errors else "blocked",
        "manifest": str(path.resolve()),
        "manifest_sha256": _digest_file(path),
        "project_id": manifest.get("project_id"),
        "source_reference": source_reference,
        "source_sha256": source_hash,
        "content_inventory": str(content_inventory_path.resolve()) if content_inventory_path else None,
        "chart_count": len(charts),
        "charts": chart_summaries,
        "errors": errors,
        "warnings": warnings,
        "human_visual_review_required": True,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--require-source", action="store_true", help="block when source_reference is not a local file")
    parser.add_argument("--content-inventory", help="require one-to-one chart coverage and route/status agreement")
    parser.add_argument("--report")
    args = parser.parse_args()
    result = validate(
        Path(args.manifest).resolve(),
        require_source=args.require_source,
        content_inventory_path=Path(args.content_inventory).resolve() if args.content_inventory else None,
    )
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("valid") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
