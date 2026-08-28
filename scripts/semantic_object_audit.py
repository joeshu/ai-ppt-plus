#!/usr/bin/env python3
"""Audit the semantic meaning of final PPTX objects against manifests."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"manifest must be an object: {path}")
    return value


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normal_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").replace("\v", "\n")


def _resolve(base: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = value.split("#", 1)[0]
    if not candidate:
        return None
    path = Path(candidate)
    return path if path.is_absolute() else base / path


def _asset_records(value: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if any(key in value for key in ("asset_id", "panel_id", "icon_id", "path", "file", "copied_to")):
            records.append(value)
        for child in value.values():
            records.extend(_asset_records(child))
    elif isinstance(value, list):
        for child in value:
            records.extend(_asset_records(child))
    return records


def _record_ids(record: dict[str, Any]) -> set[str]:
    return {str(record[key]) for key in ("asset_id", "panel_id", "icon_id", "object_id") if record.get(key)}


def _record_paths(record: dict[str, Any]) -> set[str]:
    values = set()
    for key in ("path", "file", "source", "source_path", "copied_to"):
        value = record.get(key)
        if isinstance(value, str) and value:
            values.add(value.split("#", 1)[0])
    return values


def _values(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value] if value else []


def _hash_candidates(obj: dict[str, Any], assets: list[dict[str, Any]], base: Path) -> tuple[set[str], list[Path]]:
    details = obj.get("details") if isinstance(obj.get("details"), dict) else {}
    hashes = set()
    paths: list[Path] = []
    for source in (obj, details):
        for key in ("source_hash", "path_sha256", "sha256"):
            value = source.get(key)
            if isinstance(value, str) and SHA256.fullmatch(value):
                hashes.add(value.lower())
        for key in ("source_path", "path", "file", "copied_to"):
            path = _resolve(base, source.get(key))
            if path is not None:
                paths.append(path)

    wanted_ids = {str(value) for value in _values(obj.get("asset_ids")) if value}
    if obj.get("embedded_asset"):
        wanted_ids.add(str(obj["embedded_asset"]))
    wanted_paths = {str(value).split("#", 1)[0] for value in _values(obj.get("source_paths")) if value}
    wanted_paths.update(str(value).split("#", 1)[0] for value in _values(obj.get("source_path")) if value)
    for record in assets:
        if wanted_ids and not wanted_ids.intersection(_record_ids(record)):
            continue
        record_paths = _record_paths(record)
        if wanted_paths and not wanted_paths.intersection(record_paths):
            continue
        if not wanted_ids and not wanted_paths:
            continue
        for key in ("source_hash", "path_sha256", "sha256"):
            value = record.get(key)
            if isinstance(value, str) and SHA256.fullmatch(value):
                hashes.add(value.lower())
        for key in ("path", "file", "source", "source_path", "copied_to"):
            path = _resolve(base, record.get(key))
            if path is not None:
                paths.append(path)
    unique_paths = []
    seen = set()
    for path in paths:
        resolved = path.resolve()
        if str(resolved) not in seen:
            seen.add(str(resolved))
            unique_paths.append(resolved)
    return hashes, unique_paths


def _shape_media(shape):
    """Return (package part name, bytes) for a picture shape, when available."""
    from pptx.oxml.ns import qn

    for element in shape._element.iter():
        if element.tag != qn("a:blip"):
            continue
        relationship_id = element.get(qn("r:embed"))
        relationship = shape.part.rels.get(relationship_id) if relationship_id else None
        if relationship is None or not hasattr(relationship, "target_part"):
            return None, None
        part = relationship.target_part
        return str(part.partname).lstrip("/"), part.blob
    return None, None


def _actual_kind(shape) -> str:
    if getattr(shape, "has_table", False):
        return "editable_table"
    if getattr(shape, "has_chart", False):
        return "editable_chart"
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        return "picture"
    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        return "native_group"
    if shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
        return "native_shape"
    if getattr(shape, "has_text_frame", False):
        return "native_text"
    return "other"


def _text_from_shape(shape) -> str:
    return _normal_text(getattr(shape, "text", ""))


def _table_evidence(shape) -> dict[str, Any]:
    table = shape.table
    rows = [[_text_from_shape(cell) for cell in row.cells] for row in table.rows]
    return {
        "rows": len(table.rows),
        "columns": len(table.columns),
        "nonempty_cells": sum(bool(cell.strip()) for row in rows for cell in row),
        "values": rows,
    }


def _chart_evidence(shape) -> dict[str, Any]:
    chart = shape.chart
    series_count = len(chart.series)
    nonempty_series = 0
    for series in chart.series:
        try:
            values = list(series.values)
        except Exception:
            values = []
        if values:
            nonempty_series += 1
    chart_part = None
    for relationship in shape.part.rels.values():
        if not hasattr(relationship, "target_part"):
            continue
        part_name = str(relationship.target_part.partname).lstrip("/")
        if part_name.startswith("ppt/charts/"):
            chart_part = relationship.target_part
            break
    chart_xml = chart_part.blob if chart_part is not None else b""
    embedded_workbook = False
    if chart_part is not None:
        embedded_workbook = any(
            hasattr(rel, "target_part") and "embeddings/" in str(rel.target_part.partname)
            for rel in chart_part.rels.values()
        )
    return {
        "series": series_count,
        "nonempty_series": nonempty_series,
        "has_cached_values": b"<c:numCache" in chart_xml or b"<c:strCache" in chart_xml,
        "has_embedded_workbook": embedded_workbook,
        "chart_part": str(chart_part.partname).lstrip("/") if chart_part is not None else None,
    }


def _expected_text(obj: dict[str, Any], text_specs: dict[str, dict[str, Any]]) -> str | None:
    spec = obj.get("text_spec") if isinstance(obj.get("text_spec"), dict) else None
    if spec is None:
        spec = text_specs.get(str(obj.get("text_id") or obj.get("object_id")))
    if spec is None or "content" not in spec:
        return None
    return _normal_text(spec.get("content"))


def _type_matches(expected: str, actual: str) -> bool:
    if expected == "editable_text":
        return actual == "native_text"
    if expected == "editable_table":
        return actual == "editable_table"
    if expected == "editable_chart":
        return actual == "editable_chart"
    if expected in {"native_shape", "native_group"}:
        return actual == expected
    if expected == "editable_vector":
        return actual == "picture"
    if expected in {"independent_image", "extracted_icon", "traceable_static_graphic"}:
        return actual == "picture"
    return True


def audit(deck_path: Path, object_manifest_path: Path, text_manifest_path: Path | None = None, asset_manifest_paths: list[Path] | None = None) -> dict[str, Any]:
    from pptx import Presentation

    object_manifest = _read(object_manifest_path)
    text_specs: dict[str, dict[str, Any]] = {}
    if text_manifest_path and text_manifest_path.is_file():
        text_manifest = _read(text_manifest_path)
        for slide in text_manifest.get("slides", []):
            for spec in slide.get("text_specs", []) if isinstance(slide, dict) else []:
                if isinstance(spec, dict) and spec.get("text_id"):
                    text_specs[str(spec["text_id"])] = spec
    asset_records: list[dict[str, Any]] = []
    for path in asset_manifest_paths or []:
        if path.is_file():
            asset_records.extend(_asset_records(_read(path)))

    prs = Presentation(str(deck_path))
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    audited: list[dict[str, Any]] = []
    expected_count = 0
    seen_expected = set()
    for slide_index, slide_spec in enumerate(object_manifest.get("slides", []), 1):
        if not isinstance(slide_spec, dict):
            continue
        slide_no = int(slide_spec.get("slide_no", slide_index))
        if slide_no < 1 or slide_no > len(prs.slides):
            errors.append({"code": "manifest_slide_missing", "slide_no": slide_no})
            continue
        shapes = list(prs.slides[slide_no - 1].shapes)
        by_name: dict[str, list[Any]] = {}
        for shape in shapes:
            by_name.setdefault(shape.name, []).append(shape)
        for obj in slide_spec.get("objects", []):
            if not isinstance(obj, dict):
                continue
            expected_count += 1
            object_id = str(obj.get("object_id", ""))
            seen_expected.add((slide_no, object_id))
            matches = by_name.get(object_id, [])
            if not matches:
                errors.append({"code": "semantic_object_missing", "slide_no": slide_no, "object_id": object_id})
                continue
            if len(matches) != 1:
                errors.append({"code": "semantic_object_name_not_unique", "slide_no": slide_no, "object_id": object_id, "observed": len(matches)})
                continue
            shape = matches[0]
            actual = _actual_kind(shape)
            expected_type = str(obj.get("object_type", ""))
            record: dict[str, Any] = {
                "slide_no": slide_no,
                "object_id": object_id,
                "role": obj.get("role"),
                "expected_type": expected_type,
                "actual_type": actual,
                "shape_type": str(shape.shape_type),
                "text": _text_from_shape(shape),
                "semantic_checks": {},
            }
            if not _type_matches(expected_type, actual):
                errors.append({"code": "semantic_type_mismatch", "slide_no": slide_no, "object_id": object_id, "expected": expected_type, "actual": actual})
            record["semantic_checks"]["type"] = actual == "native_text" if expected_type == "editable_text" else _type_matches(expected_type, actual)

            expected_text = _expected_text(obj, text_specs)
            if expected_text is not None:
                observed_text = _text_from_shape(shape)
                matches_text = expected_text == observed_text
                record["semantic_checks"]["text_exact"] = matches_text
                if not matches_text:
                    errors.append({"code": "pptx_text_manifest_mismatch", "slide_no": slide_no, "object_id": object_id, "expected": expected_text, "observed": observed_text})

            if actual == "editable_table":
                table = _table_evidence(shape)
                record["table"] = table
                valid_table = table["rows"] > 0 and table["columns"] > 0
                record["semantic_checks"]["native_table_data"] = valid_table
                if not valid_table:
                    errors.append({"code": "native_table_empty", "slide_no": slide_no, "object_id": object_id})
            if actual == "editable_chart":
                chart = _chart_evidence(shape)
                record["chart"] = chart
                valid_chart = chart["series"] > 0 and chart["nonempty_series"] > 0 and chart["has_cached_values"] and chart["has_embedded_workbook"]
                record["semantic_checks"]["native_chart_data"] = valid_chart
                if not valid_chart:
                    errors.append({"code": "native_chart_data_missing", "slide_no": slide_no, "object_id": object_id, "evidence": chart})

            is_brand_lockup = obj.get("role") in {"brand_lockup", "logo", "brand-logo"} or obj.get("asset_policy") == "brand_lockup" or (isinstance(obj.get("details"), dict) and obj["details"].get("asset_policy") == "brand_lockup")
            if is_brand_lockup:
                brand_ok = actual == "picture" and not _text_from_shape(shape)
                record["semantic_checks"]["brand_lockup_whole_asset"] = brand_ok
                if not brand_ok:
                    errors.append({"code": "brand_lockup_not_whole_picture", "slide_no": slide_no, "object_id": object_id, "actual": actual})

            if actual == "picture":
                part_name, blob = _shape_media(shape)
                record["media_part"] = part_name
                record["embedded_sha256"] = hashlib.sha256(blob).hexdigest() if blob is not None else None
                expected_hashes, source_paths = _hash_candidates(obj, asset_records, object_manifest_path.parent)
                for source_path in source_paths:
                    if source_path.is_file():
                        source_hash = _digest(source_path)
                        expected_hashes.add(source_hash)
                    else:
                        warnings.append({"code": "source_file_unavailable", "slide_no": slide_no, "object_id": object_id, "path": str(source_path)})
                if expected_hashes and blob is not None:
                    hash_ok = hashlib.sha256(blob).hexdigest().lower() in expected_hashes
                    record["semantic_checks"]["source_hash"] = hash_ok
                    if not hash_ok:
                        errors.append({"code": "embedded_asset_hash_mismatch", "slide_no": slide_no, "object_id": object_id, "expected": sorted(expected_hashes), "observed": record["embedded_sha256"]})
                elif expected_hashes and blob is None:
                    errors.append({"code": "embedded_asset_unreadable", "slide_no": slide_no, "object_id": object_id})

            audited.append(record)

    result = {
        "schema": "ai-ppt-plus/semantic-object-audit/v1",
        "valid": not errors,
        "status": "passed" if not errors else "blocked",
        "deck": str(deck_path.resolve()),
        "deck_sha256": _digest(deck_path),
        "object_manifest": str(object_manifest_path.resolve()),
        "text_manifest": str(text_manifest_path.resolve()) if text_manifest_path else None,
        "expected_object_count": expected_count,
        "audited_object_count": len(audited),
        "objects": audited,
        "errors": errors,
        "warnings": warnings,
        "human_visual_review_required": True,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck")
    parser.add_argument("--object-manifest", required=True)
    parser.add_argument("--text-manifest")
    parser.add_argument("--asset-manifest", action="append", default=[])
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        result = audit(
            Path(args.deck).resolve(),
            Path(args.object_manifest).resolve(),
            Path(args.text_manifest).resolve() if args.text_manifest else None,
            [Path(path).resolve() for path in args.asset_manifest],
        )
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/semantic-object-audit/v1", "valid": False, "status": "invalid", "errors": [{"code": "runtime_error", "message": f"{type(exc).__name__}: {exc}"}]}
    if args.report:
        report = Path(args.report).resolve()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("valid") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
