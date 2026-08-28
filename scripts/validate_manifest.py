#!/usr/bin/env python3
"""Validate slide/visual/asset/handoff JSON and optional L0-L5 editability."""

import argparse
import hashlib
import json
from pathlib import Path

from atomic_output import atomic_write_json
from editability import compare_summary, summarize_objects, validate_objects


TYPES = {"title", "agenda", "section", "comparison", "timeline", "process", "framework", "matrix", "funnel", "pyramid", "map", "chart", "table", "infographic", "scene", "quote", "summary", "appendix"}
STATES = {"intake", "source-analyzed", "outline-draft", "outline-review", "narrative-approved", "design-system-ready", "visual-draft", "visual-approved", "reconstruction", "rendered", "validated", "revision-required", "human-closeout", "delivered", "draft", "approved", "blocked", "placeholder", "complete"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--kind", choices=["auto", "slide", "visual", "asset", "handoff"], default="auto")
    parser.add_argument("--asset-manifest", help="optional external asset manifest for slide/visual orphan-reference checks")
    parser.add_argument("--require-editability", action="store_true", help="require per-object L0-L5 records and a matching page summary")
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        data = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"valid": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 3
    if not isinstance(data, dict):
        output = {"schema": "ai-ppt-plus/manifest-validation/v1", "kind": args.kind, "valid": False, "items": 0, "issues": [{"severity": "blocker", "code": "manifest_not_object"}], "warnings": []}
        print(json.dumps(output, ensure_ascii=False))
        return 2

    kind = args.kind if args.kind != "auto" else data.get("kind", "slide")
    key = "slides" if kind in {"slide", "visual"} else "assets" if kind == "asset" else "batches"
    items = data.get(key, [])
    issues = []
    warnings = []
    editability_evidence = []
    seen = set()
    known = {str(item.get("asset_id")) for item in (data.get("assets") or []) if isinstance(item, dict)}
    root_state = data.get("state")

    if args.asset_manifest:
        try:
            external = json.loads(Path(args.asset_manifest).read_text(encoding="utf-8"))
            known |= {str(item.get("asset_id")) for item in (external.get("assets") or []) if isinstance(item, dict)}
        except Exception as exc:
            issues.append({"severity": "blocker", "code": "asset_manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"})
    if not isinstance(items, list):
        issues.append({"severity": "blocker", "code": "items_not_array"})
        items = []
    if kind in {"slide", "visual"} and not items:
        issues.append({"severity": "blocker", "code": "slide_items_missing"})
    if kind in {"slide", "visual"} and args.require_editability and data.get("editability_protocol") != "L0-L5/v1":
        issues.append({"severity": "blocker", "code": "editability_protocol_missing_or_invalid", "expected": "L0-L5/v1", "observed": data.get("editability_protocol")})
    if kind in {"slide", "visual"} and "gate_requirements" in data:
        gate_requirements = data.get("gate_requirements")
        gate_names = ("object_manifest", "semantic_object_audit", "manifest_registry", "text_model", "text_style_map", "icon_assets", "imagegen_assets", "panel_assets", "panel_approval", "gradient_visual", "source_image_validation", "reference_audit")
        if not isinstance(gate_requirements, dict):
            issues.append({"severity": "blocker", "code": "gate_requirements_not_object"})
        else:
            for name in gate_names:
                if not isinstance(gate_requirements.get(name), bool):
                    issues.append({"severity": "blocker", "code": "gate_requirement_not_boolean", "field": name})

    slide_numbers = []

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            issues.append({"severity": "blocker", "code": "item_not_object", "index": index})
            continue
        ident = item.get("slide_no", item.get("asset_id", item.get("batch_id")))
        if ident in seen:
            issues.append({"severity": "blocker", "code": "duplicate_id", "id": ident})
        seen.add(ident)
        if kind in {"slide", "visual"}:
            if item.get("slide_no") is not None:
                try:
                    slide_numbers.append(int(item.get("slide_no")))
                except (TypeError, ValueError):
                    issues.append({"severity": "blocker", "code": "invalid_slide_number", "index": index, "value": item.get("slide_no")})
            for flag in ("requires_icon_assets", "requires_imagegen_assets"):
                if flag in item and not isinstance(item.get(flag), bool):
                    issues.append({"severity": "blocker", "code": "slide_gate_requirement_not_boolean", "index": index, "field": flag})
            fields = ("slide_no", "page_type", "formal_content_source", "visual_source")
        elif kind == "asset":
            fields = ("asset_id", "path", "status", "provenance")
        else:
            fields = ("batch_id", "state", "completed_pages", "pending_pages", "next_action")
        for field in fields:
            if item.get(field) in (None, ""):
                severity = "blocker" if (kind in {"slide", "visual"} and field in {"slide_no", "page_type", "formal_content_source", "visual_source", "state", "batch_id"}) or (kind == "asset" and field in {"asset_id", "path", "provenance"}) else "major"
                issues.append({"severity": severity, "code": "missing_field", "index": index, "field": field})
        if kind in {"slide", "visual"}:
            state = item.get("state") or root_state
            if not state:
                issues.append({"severity": "blocker", "code": "missing_field", "index": index, "field": "state"})
            elif state not in STATES:
                issues.append({"severity": "blocker", "code": "invalid_state", "index": index, "value": state})
            if item.get("page_type") not in TYPES:
                issues.append({"severity": "blocker", "code": "invalid_page_type", "index": index})
            for asset_id in (item.get("asset_ids") or []):
                if known and str(asset_id) not in known:
                    issues.append({"severity": "blocker", "code": "orphan_asset_reference", "index": index, "asset_id": asset_id})

            objects_present = "objects" in item
            objects = item.get("objects")
            if not objects_present:
                if args.require_editability:
                    issues.append({"severity": "blocker", "code": "editability_object_list_missing", "slide_no": item.get("slide_no")})
                    editability_evidence.append({"slide_no": item.get("slide_no"), "status": "missing"})
                else:
                    warnings.append({"severity": "major", "code": "editability_legacy_untyped", "slide_no": item.get("slide_no")})
                    editability_evidence.append({"slide_no": item.get("slide_no"), "status": "legacy-untyped"})
            elif not isinstance(objects, list):
                issue = {"severity": "blocker", "code": "editability_objects_not_array", "slide_no": item.get("slide_no")}
                issues.append(issue)
                editability_evidence.append({"slide_no": item.get("slide_no"), "status": "invalid"})
            else:
                object_issues = validate_objects(objects)
                for object_issue in object_issues:
                    enriched = dict(object_issue)
                    enriched["slide_no"] = item.get("slide_no")
                    issues.append(enriched)
                summary = summarize_objects(objects)
                summary_issues = compare_summary(item.get("editability"), summary)
                if item.get("editability") is None:
                    if args.require_editability:
                        issues.append({"severity": "blocker", "code": "editability_summary_missing", "slide_no": item.get("slide_no")})
                    else:
                        warnings.append({"severity": "major", "code": "editability_summary_missing", "slide_no": item.get("slide_no")})
                for summary_issue in summary_issues:
                    enriched = dict(summary_issue)
                    enriched["slide_no"] = item.get("slide_no")
                    issues.append(enriched)
                editability_evidence.append({"slide_no": item.get("slide_no"), "status": "typed", "summary": summary, "issues": object_issues + summary_issues})

    if kind in {"slide", "visual"} and slide_numbers:
        if len(slide_numbers) != len(set(slide_numbers)):
            issues.append({"severity": "blocker", "code": "duplicate_slide_number", "observed": slide_numbers})
        expected_slide_numbers = list(range(1, len(items) + 1))
        if sorted(slide_numbers) != expected_slide_numbers:
            issues.append({"severity": "blocker", "code": "slide_numbers_not_contiguous", "expected": expected_slide_numbers, "observed": sorted(slide_numbers)})

    valid = not any(issue.get("severity") == "blocker" for issue in issues)
    output = {
        "schema": "ai-ppt-plus/manifest-validation/v1",
        "manifest_path": str(Path(args.manifest).resolve()),
        "manifest_sha256": sha256(Path(args.manifest)),
        "kind": kind,
        "valid": valid,
        "items": len(items),
        "issues": issues,
        "warnings": warnings,
        "editability_protocol": "L0-L5/v1" if kind in {"slide", "visual"} else None,
        "editability": editability_evidence,
    }
    if args.report:
        report = Path(args.report)
        atomic_write_json(report.resolve(), output)
    print(json.dumps(output, ensure_ascii=False))
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
