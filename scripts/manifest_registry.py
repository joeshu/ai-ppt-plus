#!/usr/bin/env python3
"""Build and validate the canonical cross-manifest registry."""
import argparse
import hashlib
import json
import sys
from pathlib import Path


SCHEMA = "ai-ppt-plus/manifest-registry/v1"
VALIDATION_SCHEMA = "ai-ppt-plus/manifest-registry-validation/v1"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def path_ref(path, base):
    try:
        return str(Path(path).resolve().relative_to(Path(base).resolve()))
    except ValueError:
        return str(Path(path).resolve())


def first(item, *keys):
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def items_from(data, keys):
    for key in keys:
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, list):
            return value
    return []


def normalize_asset(item, source):
    asset_id = first(item, "asset_id", "panel_id", "icon_id", "id")
    if not asset_id:
        return None
    output = {
        "asset_id": asset_id,
        "role": first(item, "role", "asset_role") or "asset",
        "path": first(item, "asset_path", "path", "file", "output_path"),
        "source_ref": first(item, "source_ref", "provenance", "source"),
        "source_bbox": first(item, "source_bbox", "bbox", "box"),
        "strategy": first(item, "strategy", "extraction_method", "method"),
        "editability_level": first(item, "editability_level", "level"),
        "embedded": item.get("embedded"),
        "render_visible": item.get("render_visible"),
        "source_manifest": source,
    }
    output = {key: value for key, value in output.items() if value is not None}
    output["details"] = item
    return output


def normalize_object(item, source):
    output = {
        "object_id": first(item, "object_id", "id"),
        "role": first(item, "role", "object_role") or "object",
        "object_type": first(item, "object_type", "type") or "unresolved",
        "editability_level": first(item, "editability_level", "level") or "L5",
        "required_for_delivery": item.get("required_for_delivery", False),
        "human_review_required": item.get("human_review_required", True),
        "bbox": first(item, "bbox", "source_bbox"),
        "z_index": first(item, "z_index", "z"),
        "source_hash": item.get("source_hash"),
        "expected_kind": item.get("expected_kind"),
        "editability": item.get("editability"),
        "embedded_asset": item.get("embedded_asset"),
        "validation_status": item.get("validation_status"),
        "source_manifest": source,
    }
    output = {key: value for key, value in output.items() if value is not None}
    output["details"] = item
    return output


def build(args):
    output = Path(args.output).resolve()
    base = output.parent
    slide_data = load(args.slide_manifest)
    object_data = load(args.object_manifest) if args.object_manifest else {}
    layout_data = load(args.layout) if args.layout else {}
    objects_by_slide = {}
    for slide in object_data.get("slides", []):
        objects_by_slide[slide.get("slide_no")] = slide.get("objects", [])
    layout_by_slide = {slide.get("slide_no"): slide for slide in layout_data.get("slides", [])}

    assets = []
    asset_ids = set()
    for manifest_path in args.asset_manifest:
        data = load(manifest_path)
        source = path_ref(manifest_path, base)
        for item in items_from(data, ("assets", "panels", "icons")):
            if not isinstance(item, dict):
                continue
            asset = normalize_asset(item, source)
            if asset and asset["asset_id"] not in asset_ids:
                assets.append(asset)
                asset_ids.add(asset["asset_id"])

    slides = []
    for slide in slide_data.get("slides", []):
        number = slide.get("slide_no")
        layout = layout_by_slide.get(number, {})
        regions = []
        for region in layout.get("regions", layout.get("panels", [])):
            if not isinstance(region, dict):
                continue
            region_id = first(region, "region_id", "panel_id", "id")
            if region_id:
                regions.append({
                    "region_id": region_id,
                    "bbox": first(region, "bbox", "source_bbox"),
                    "object_id": first(region, "object_id", "panel_id"),
                    "role": first(region, "role") or "semantic-panel",
                    "source_ref": first(region, "source_ref", "provenance"),
                    "independent": region.get("independent", True),
                })
        slide_objects = slide.get("objects") or objects_by_slide.get(number, [])
        normalized_objects = [normalize_object(item, "slide-object-manifest.json") for item in slide_objects if isinstance(item, dict)]
        text_runs = []
        for obj in normalized_objects:
            if obj.get("object_type") == "editable_text":
                details = obj.get("details", {})
                text_runs.extend(details.get("runs", []))
        slides.append({
            "slide_id": first(slide, "slide_id", "id") or f"S{int(number):02d}",
            "slide_no": number,
            "page_type": slide.get("page_type"),
            "geometry_ref": first(slide, "layout_ref", "reference_image") or "layout.json",
            "regions": regions,
            "objects": normalized_objects,
            "text_runs": text_runs,
            "asset_ids": slide.get("asset_ids", []),
            "gate_refs": slide.get("gate_refs", []),
        })
    sources = []
    for name, path in (("slide_manifest", args.slide_manifest), ("object_manifest", args.object_manifest), ("layout", args.layout), ("report_index", args.report_index)):
        if path:
            sources.append({"source_id": name, "path": path_ref(path, base), "sha256": digest(path)})
    registry = {
        "schema": SCHEMA,
        "project_id": args.project_id,
        "revision": args.revision,
        "state": args.state,
        "deck": {"path": path_ref(args.deck, base), "sha256": digest(args.deck)},
        "authority": {"formal_content": args.formal_content_source, "visual": args.visual_source},
        "sources": sources,
        "slides": slides,
        "assets": assets,
        "gates": [],
        "evidence": {"slide_manifest": path_ref(args.slide_manifest, base), "object_manifest": path_ref(args.object_manifest, base) if args.object_manifest else None, "asset_manifests": [path_ref(p, base) for p in args.asset_manifest], "report_index": path_ref(args.report_index, base) if args.report_index else None},
    }
    if args.report_index:
        report_data = load(args.report_index)
        registry["gates"] = [{**entry, "path": entry.get("path"), "source": path_ref(args.report_index, base)} for entry in report_data.get("reports", []) if isinstance(entry, dict)]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, "output": str(output), "slides": len(slides), "assets": len(assets)}, ensure_ascii=False))
    return 0


def validate(args):
    issues, warnings = [], []
    path = Path(args.registry).resolve()
    try:
        data = load(path)
    except Exception as exc:
        issues.append({"code": "invalid_json", "message": str(exc)})
        data = {}
    if data.get("schema") != SCHEMA:
        issues.append({"code": "schema_mismatch"})
    for key in ("project_id", "revision", "deck", "slides", "assets", "gates"):
        if key not in data:
            issues.append({"code": "missing_required_field", "field": key})
    deck_path = Path(args.deck).resolve() if args.deck else None
    if deck_path and deck_path.is_file():
        actual = digest(deck_path)
        if actual != data.get("deck", {}).get("sha256"):
            issues.append({"code": "deck_hash_mismatch", "expected": data.get("deck", {}).get("sha256"), "actual": actual})
    elif deck_path:
        issues.append({"code": "deck_missing", "path": str(deck_path)})
    slides = data.get("slides", []) if isinstance(data.get("slides"), list) else []
    slide_nos = [s.get("slide_no") for s in slides if isinstance(s, dict)]
    if len(slide_nos) != len(set(slide_nos)):
        issues.append({"code": "duplicate_slide_number"})
    object_ids, asset_ids = set(), {a.get("asset_id") for a in data.get("assets", []) if isinstance(a, dict)}
    for slide in slides:
        for obj in slide.get("objects", []):
            oid = obj.get("object_id")
            if oid in object_ids:
                issues.append({"code": "duplicate_object_id", "object_id": oid})
            object_ids.add(oid)
            if obj.get("object_type") in {"independent_image", "traceable_static_graphic", "extracted_icon"} and obj.get("details", {}).get("contains_formal_content") is True:
                issues.append({"code": "formal_content_in_raster_asset", "object_id": oid})
        for aid in slide.get("asset_ids", []):
            if aid not in asset_ids and aid not in object_ids:
                warnings.append({"code": "unresolved_asset_reference", "asset_id": aid, "slide_no": slide.get("slide_no")})
        region_ids = [r.get("region_id") for r in slide.get("regions", [])]
        if len(region_ids) != len(set(region_ids)):
            issues.append({"code": "duplicate_region_id", "slide_no": slide.get("slide_no")})
    for gate in data.get("gates", []):
        if not isinstance(gate, dict):
            issues.append({"code": "invalid_gate_record"})
            continue
        gate_path = gate.get("path")
        if args.report and gate_path:
            candidate = Path(gate_path)
            if not candidate.is_absolute():
                source = gate.get("source")
                source_path = Path(source) if source else Path(args.report).resolve()
                if source_path.is_file():
                    candidate = source_path.resolve().parent / candidate
                else:
                    candidate = Path(args.report).resolve().parent / candidate
            if not candidate.is_file():
                issue = {"code": "gate_report_missing", "path": str(candidate)}
                (issues if args.require_gates and gate.get("required", True) else warnings).append(issue)
            else:
                try:
                    gate_report = load(candidate)
                    if gate.get("required", True) and gate_report.get("valid") is False:
                        issues.append({"code": "required_gate_failed", "path": str(candidate)})
                except Exception as exc:
                    issues.append({"code": "gate_report_invalid_json", "path": str(candidate), "message": str(exc)})
    if args.require_gates and not data.get("gates"):
        issues.append({"code": "required_gates_missing"})
    result = {"schema": VALIDATION_SCHEMA, "valid": not issues, "status": "passed" if not issues else "blocked", "issues": issues, "warnings": warnings, "slide_count": len(slides), "object_count": len(object_ids), "asset_count": len(asset_ids), "registry_sha256": digest(path) if path.is_file() else None, "deck_sha256": data.get("deck", {}).get("sha256")}
    if args.report:
        report = Path(args.report).resolve(); report.parent.mkdir(parents=True, exist_ok=True); report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--output", required=True); build_parser.add_argument("--project-id", required=True); build_parser.add_argument("--revision", default="working"); build_parser.add_argument("--state", default="validated"); build_parser.add_argument("--deck", required=True); build_parser.add_argument("--slide-manifest", required=True); build_parser.add_argument("--object-manifest"); build_parser.add_argument("--layout"); build_parser.add_argument("--asset-manifest", action="append", default=[]); build_parser.add_argument("--report-index"); build_parser.add_argument("--formal-content-source", default="slide-manifest.json"); build_parser.add_argument("--visual-source", default="reference image / visual manifest"); build_parser.set_defaults(func=build)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("registry"); validate_parser.add_argument("--deck"); validate_parser.add_argument("--report"); validate_parser.add_argument("--require-gates", action="store_true"); validate_parser.set_defaults(func=validate)
    parsed = parser.parse_args()
    return parsed.func(parsed)


if __name__ == "__main__":
    raise SystemExit(main())
