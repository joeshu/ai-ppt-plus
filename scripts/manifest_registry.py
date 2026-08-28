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

from atomic_output import atomic_write_json
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
    atomic_write_json(output.resolve(), registry)
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
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            _append_issue(issues, "source_id_missing")
        elif source_id in source_ids:
            _append_issue(issues, "duplicate_source_id", source_id=source_id)
        source_ids.add(source_id)
        source_path = _resolve_registry_ref(source.get("path"), registry_path.parent)
        required = source.get("required", False)
        if source_path is None or not source_path.is_file():
            target = issues if required else warnings
            _append_issue(target, "required_source_missing" if required else "source_missing", source_id=source_id, path=str(source_path) if source_path else None)
            continue
        declared = source.get("sha256")
        if declared is not None and not valid_sha256(declared):
            _append_issue(issues, "source_hash_invalid", source_id=source_id, value=declared)
        elif declared and digest(source_path) != declared:
            _append_issue(issues, "source_manifest_hash_mismatch", source_id=source_id, path=str(source_path))


def _validate_gate_records(data: dict[str, Any], registry_path: Path, deck_hash: str | None, args: argparse.Namespace, issues: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    gates = data.get("gates")
    if not isinstance(gates, list):
        _append_issue(issues, "gates_not_array")
        return
    gate_ids = set()
    for gate in gates:
        if not isinstance(gate, dict):
            _append_issue(issues, "invalid_gate_record")
            continue
        gate_id = str(first(gate, "gate_id", "report_type", "id") or "")
        if not gate_id:
            _append_issue(issues, "gate_id_missing")
        elif gate_id in gate_ids:
            _append_issue(issues, "duplicate_gate_id", gate_id=gate_id)
        gate_ids.add(gate_id)
        required = gate.get("required", True)
        gate_path = gate.get("path")
        source_path = _resolve_registry_ref(gate.get("source"), registry_path.parent)
        base = source_path.parent if source_path and source_path.is_file() else registry_path.parent
        candidate = _resolve_registry_ref(gate_path, base)
        if candidate is None or not candidate.is_file():
            target = issues if args.require_gates and required else warnings
            _append_issue(target, "gate_report_missing" if required else "optional_gate_missing", gate_id=gate_id, path=str(candidate) if candidate else None)
            continue
        try:
            report = load(candidate)
        except Exception as exc:
            _append_issue(issues, "gate_report_invalid_json", gate_id=gate_id, message=f"{type(exc).__name__}: {exc}")
            continue
        if required and report.get("valid") is False:
            _append_issue(issues, "required_gate_failed", gate_id=gate_id, path=str(candidate))
        report_deck_hash = report.get("deck_sha256")
        if deck_hash and report_deck_hash and report_deck_hash != deck_hash:
            _append_issue(issues, "gate_deck_hash_mismatch", gate_id=gate_id, expected=deck_hash, observed=report_deck_hash)
    if args.require_gates and not gates:
        _append_issue(issues, "required_gates_missing")


def validate(args: argparse.Namespace) -> int:
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    path = Path(args.registry).resolve()
    try:
        data = load(path)
    except Exception as exc:
        data = {}
        _append_issue(issues, "invalid_json", message=f"{type(exc).__name__}: {exc}")
    if not isinstance(data, dict):
        data = {}
        _append_issue(issues, "registry_not_object")

    schema = data.get("schema")
    legacy = schema in LEGACY_SCHEMAS
    if schema != SCHEMA and not legacy:
        _append_issue(issues, "schema_mismatch", expected=SCHEMA, observed=schema)
    if legacy:
        warnings.append({"code": "legacy_registry_schema", "schema": schema, "migration": "rebuild with manifest_registry.py build"})
    if not legacy:
        model = data.get("model")
        if not isinstance(model, dict) or model.get("name") != MODEL_NAME or model.get("version") != MODEL_VERSION:
            _append_issue(issues, "model_contract_mismatch", expected={"name": MODEL_NAME, "version": MODEL_VERSION}, observed=model)

    required_fields = ("project_id", "revision", "deck", "slides", "assets", "gates")
    if not legacy:
        required_fields += ("model", "authority", "sources", "evidence")
    for key in required_fields:
        if key not in data:
            _append_issue(issues, "missing_required_field", field=key)
    authority = data.get("authority")
    if not isinstance(authority, dict):
        _append_issue(issues, "authority_not_object")
    elif not legacy:
        for field in ("formal_content", "visual", "geometry", "semantic_objects", "assets"):
            if field not in authority:
                _append_issue(issues, "authority_field_missing", field=field)
    deck_record = data.get("deck") if isinstance(data.get("deck"), dict) else {}
    deck_path = Path(args.deck).resolve() if args.deck else None
    if deck_path and deck_path.is_file():
        actual = digest(deck_path)
        if actual != deck_record.get("sha256"):
            _append_issue(issues, "deck_hash_mismatch", expected=deck_record.get("sha256"), actual=actual)
    elif deck_path:
        _append_issue(issues, "deck_missing", path=str(deck_path))
    if deck_record.get("sha256") is not None and not valid_sha256(deck_record.get("sha256")):
        _append_issue(issues, "deck_hash_invalid", value=deck_record.get("sha256"))

    _validate_source_records(data, path, issues, warnings)

    raw_assets = data.get("assets") if isinstance(data.get("assets"), list) else []
    if not isinstance(data.get("assets"), list):
        _append_issue(issues, "assets_not_array")
    assets_by_id: dict[str, dict[str, Any]] = {}
    for index, asset in enumerate(raw_assets, 1):
        if not isinstance(asset, dict):
            _append_issue(issues, "asset_not_object", index=index)
            continue
        asset_id = asset.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id:
            _append_issue(issues, "asset_id_missing", index=index)
        elif asset_id in assets_by_id:
            _append_issue(issues, "duplicate_asset_id", asset_id=asset_id)
        else:
            assets_by_id[asset_id] = asset
        level = asset.get("editability_level")
        if level is not None and level not in EDITABILITY_LEVELS:
            _append_issue(issues, "invalid_asset_editability_level", asset_id=asset_id, value=level)
        if not asset.get("source_ref"):
            warnings.append({"code": "asset_source_ref_missing", "asset_id": asset_id})
        source_hash = asset.get("source_hash")
        if source_hash is not None and not valid_sha256(source_hash):
            _append_issue(issues, "asset_source_hash_invalid", asset_id=asset_id, value=source_hash)
        path_hash = asset.get("path_sha256")
        if path_hash is not None and not valid_sha256(path_hash):
            _append_issue(issues, "asset_path_hash_invalid", asset_id=asset_id, value=path_hash)
        resolved = _resolve_path(asset.get("path"), asset.get("path_base"), path.parent)
        if asset.get("path") and resolved:
            if not resolved.is_file():
                target = issues if asset.get("required_for_delivery") is True else warnings
                _append_issue(target, "required_asset_missing" if asset.get("required_for_delivery") is True else "asset_file_missing", asset_id=asset_id, path=str(resolved))
            elif path_hash and digest(resolved) != path_hash:
                _append_issue(issues, "asset_path_hash_mismatch", asset_id=asset_id, path=str(resolved))
        if asset.get("required_for_delivery") is not None and not isinstance(asset.get("required_for_delivery"), bool):
            _append_issue(issues, "asset_required_flag_invalid", asset_id=asset_id, value=asset.get("required_for_delivery"))

    raw_slides = data.get("slides") if isinstance(data.get("slides"), list) else []
    if not isinstance(data.get("slides"), list):
        _append_issue(issues, "slides_not_array")
    global_object_ids: set[str] = set()
    global_text_ids: set[str] = set()
    slide_ids: set[str] = set()
    slide_numbers: list[int] = []
    for slide_index, slide in enumerate(raw_slides, 1):
        if not isinstance(slide, dict):
            _append_issue(issues, "slide_not_object", index=slide_index)
            continue
        slide_no = slide.get("slide_no")
        slide_id = slide.get("slide_id")
        if not isinstance(slide_no, int) or isinstance(slide_no, bool) or slide_no < 1:
            _append_issue(issues, "invalid_slide_number", index=slide_index, value=slide_no)
        else:
            slide_numbers.append(slide_no)
        if not isinstance(slide_id, str) or not slide_id:
            _append_issue(issues, "slide_id_missing", slide_no=slide_no)
        elif slide_id in slide_ids:
            _append_issue(issues, "duplicate_slide_id", slide_id=slide_id)
        slide_ids.add(slide_id)

        objects = slide.get("objects")
        if not isinstance(objects, list):
            _append_issue(issues, "objects_not_array", slide_no=slide_no)
            objects = []
        local_object_ids: set[str] = set()
        for object_index, obj in enumerate(objects, 1):
            if not isinstance(obj, dict):
                _append_issue(issues, "object_not_object", slide_no=slide_no, index=object_index)
                continue
            object_id = obj.get("object_id")
            if not isinstance(object_id, str) or not object_id:
                _append_issue(issues, "object_id_missing", slide_no=slide_no, index=object_index)
            elif object_id in local_object_ids or object_id in global_object_ids:
                _append_issue(issues, "duplicate_object_id", slide_no=slide_no, object_id=object_id)
            if object_id:
                local_object_ids.add(object_id)
                global_object_ids.add(object_id)
            level = obj.get("editability_level")
            if level not in EDITABILITY_LEVELS:
                _append_issue(issues, "invalid_object_editability_level", slide_no=slide_no, object_id=object_id, value=level)
            object_type = obj.get("object_type")
            details = obj.get("details") if isinstance(obj.get("details"), dict) else {}
            if object_type in {"independent_image", "traceable_static_graphic", "extracted_icon"} and (obj.get("contains_formal_content") is True or details.get("contains_formal_content") is True):
                _append_issue(issues, "formal_content_in_raster_asset", slide_no=slide_no, object_id=object_id)
            if obj.get("role") == "formal-text" and object_type != "editable_text":
                _append_issue(issues, "formal_text_not_editable", slide_no=slide_no, object_id=object_id)
            if "bbox" in obj and obj.get("bbox") is not None and not _bbox_valid(obj.get("bbox")):
                _append_issue(issues, "invalid_object_bbox", slide_no=slide_no, object_id=object_id)
            object_asset_ids = _refs(obj.get("asset_ids"))
            if not object_asset_ids and isinstance(obj.get("embedded_asset"), str) and obj.get("embedded_asset"):
                object_asset_ids = [obj["embedded_asset"]]
            for asset_id in object_asset_ids:
                if asset_id not in assets_by_id:
                    _append_issue(issues, "unresolved_object_asset_reference", slide_no=slide_no, object_id=object_id, asset_id=asset_id)

        regions = slide.get("regions")
        if not isinstance(regions, list):
            _append_issue(issues, "regions_not_array", slide_no=slide_no)
            regions = []
        region_ids: set[str] = set()
        for region_index, region in enumerate(regions, 1):
            if not isinstance(region, dict):
                _append_issue(issues, "region_not_object", slide_no=slide_no, index=region_index)
                continue
            region_id = region.get("region_id")
            if not isinstance(region_id, str) or not region_id:
                _append_issue(issues, "region_id_missing", slide_no=slide_no, index=region_index)
            elif region_id in region_ids:
                _append_issue(issues, "duplicate_region_id", slide_no=slide_no, region_id=region_id)
            region_ids.add(region_id)
            bbox = region.get("bbox")
            polygon = region.get("polygon")
            if bbox is None and polygon is None:
                warnings.append({"code": "region_geometry_missing", "slide_no": slide_no, "region_id": region_id})
            if bbox is not None and not _bbox_valid(bbox):
                _append_issue(issues, "invalid_region_bbox", slide_no=slide_no, region_id=region_id)
            if polygon is not None and not _polygon_valid(polygon):
                _append_issue(issues, "invalid_region_polygon", slide_no=slide_no, region_id=region_id)
            for object_id in _region_refs(region, "object_ids", "object_id"):
                if object_id not in local_object_ids:
                    _append_issue(issues, "unresolved_region_object_reference", slide_no=slide_no, region_id=region_id, object_id=object_id)
            for asset_id in _region_refs(region, "asset_ids", "asset_id"):
                if asset_id not in assets_by_id:
                    _append_issue(issues, "unresolved_region_asset_reference", slide_no=slide_no, region_id=region_id, asset_id=asset_id)

        text_specs = slide.get("text_specs")
        if not isinstance(text_specs, list):
            _append_issue(issues, "text_specs_not_array", slide_no=slide_no)
            text_specs = []
        text_ids: set[str] = set()
        for text_index, spec in enumerate(text_specs, 1):
            if not isinstance(spec, dict):
                _append_issue(issues, "text_spec_not_object", slide_no=slide_no, index=text_index)
                continue
            text_id = spec.get("text_id")
            if not isinstance(text_id, str) or not text_id:
                _append_issue(issues, "text_id_missing", slide_no=slide_no, index=text_index)
                continue
            if text_id in text_ids:
                _append_issue(issues, "duplicate_text_id", slide_no=slide_no, text_id=text_id)
            elif text_id in global_text_ids:
                _append_issue(issues, "duplicate_text_id", slide_no=slide_no, text_id=text_id)
            text_ids.add(text_id)
            global_text_ids.add(text_id)
            if spec.get("slide_no") not in (None, slide_no):
                _append_issue(issues, "text_slide_number_mismatch", slide_no=slide_no, text_id=text_id, observed=spec.get("slide_no"))
            content = str(spec.get("content", ""))
            runs = spec.get("runs")
            if runs is not None and not isinstance(runs, list):
                _append_issue(issues, "text_runs_not_array", slide_no=slide_no, text_id=text_id)
            elif isinstance(runs, list):
                run_text = []
                run_ids = set()
                for run in runs:
                    if not isinstance(run, dict):
                        _append_issue(issues, "text_run_not_object", slide_no=slide_no, text_id=text_id)
                        continue
                    run_id = run.get("run_id")
                    if run_id in run_ids:
                        _append_issue(issues, "duplicate_text_run_id", slide_no=slide_no, text_id=text_id, run_id=run_id)
                    run_ids.add(run_id)
                    run_text.append(str(run.get("text", "")))
                if run_text and "".join(run_text) != content:
                    _append_issue(issues, "text_run_content_mismatch", slide_no=slide_no, text_id=text_id)
            matching = [obj for obj in objects if isinstance(obj, dict) and (obj.get("object_id") == text_id or obj.get("text_id") == text_id)]
            if not matching:
                _append_issue(issues, "text_spec_without_editable_object", slide_no=slide_no, text_id=text_id)
            elif not any(obj.get("object_type") == "editable_text" for obj in matching):
                _append_issue(issues, "text_spec_object_not_editable_text", slide_no=slide_no, text_id=text_id)
        _validate_text_specs(text_specs, slide_no, issues, warnings)

        for asset_id in _refs(slide.get("asset_ids")):
            if asset_id not in assets_by_id:
                _append_issue(issues, "unresolved_slide_asset_reference", slide_no=slide_no, asset_id=asset_id)

    if len(slide_numbers) != len(set(slide_numbers)):
        _append_issue(issues, "duplicate_slide_number")
    if slide_numbers and sorted(slide_numbers) != list(range(1, len(slide_numbers) + 1)):
        warnings.append({"code": "slide_numbers_not_contiguous", "observed": sorted(slide_numbers)})

    _validate_gate_records(data, path, deck_record.get("sha256"), args, issues, warnings)
    result = {
        "schema": VALIDATION_SCHEMA,
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "registry": str(path),
        "model": data.get("model", {"name": "legacy", "version": "1.0"}),
        "issues": issues,
        "warnings": warnings,
        "slide_count": len(raw_slides),
        "object_count": len(global_object_ids),
        "asset_count": len(assets_by_id),
        "registry_sha256": digest(path) if path.is_file() else None,
        "deck_sha256": deck_record.get("sha256"),
    }
    if args.report:
        report = Path(args.report).resolve()
        atomic_write_json(report.resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--output", required=True)
    build_parser.add_argument("--project-id", required=True)
    build_parser.add_argument("--revision", default="working")
    build_parser.add_argument("--state", default="validated")
    build_parser.add_argument("--deck", required=True)
    build_parser.add_argument("--slide-manifest", required=True)
    build_parser.add_argument("--object-manifest")
    build_parser.add_argument("--layout")
    build_parser.add_argument("--text-manifest")
    build_parser.add_argument("--asset-manifest", action="append", default=[])
    build_parser.add_argument("--report-index")
    build_parser.add_argument("--formal-content-source", default="slide-manifest.json")
    build_parser.add_argument("--visual-source", default="reference image / visual manifest")
    build_parser.set_defaults(func=build)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("registry")
    validate_parser.add_argument("--deck")
    validate_parser.add_argument("--report")
    validate_parser.add_argument("--require-gates", action="store_true")
    validate_parser.set_defaults(func=validate)
    parsed = parser.parse_args()
    try:
        return parsed.func(parsed)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "code": "manifest_registry_error", "message": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
