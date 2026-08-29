#!/usr/bin/env python3
"""Validate cross-artifact consistency for an AI PPT Plus project.

This is a read-only project-level gate. It does not rebuild or silently repair
files. It verifies handoff state, manifest structure, deck/report hashes,
page counts, ratio, and open blockers in one deterministic report.

Usage: validate_project.py PROJECT_DIR --deck DECK.pptx
       [--inspection inspection.json] [--render-report render.json]
       [--render-visual-gate gate.json] [--visual-comparison comparison.json]
       [--ocr-report ocr.json]
       [--expected-ratio 1.7777778] [--report REPORT.json]
Exit 0 when valid, 2 when a gate fails, 3 on runtime/input failure.
"""
import argparse
import hashlib
import json
from pathlib import Path

from atomic_output import atomic_write_json
from editability import summarize_objects, validate_objects


def read_json(path: Path, issues, label):
    if not path.is_file():
        issues.append({"severity": "blocker", "code": "missing_artifact", "artifact": label, "path": str(path)})
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            issues.append({"severity": "blocker", "code": "artifact_not_object", "artifact": label})
            return None
        return value
    except Exception as exc:
        issues.append({"severity": "blocker", "code": "invalid_json", "artifact": label, "message": f"{type(exc).__name__}: {exc}"})
        return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--deck", required=True)
    parser.add_argument("--inspection")
    parser.add_argument("--render-report")
    parser.add_argument("--render-visual-gate")
    parser.add_argument("--visual-comparison")
    parser.add_argument("--ocr-report")
    parser.add_argument("--content-inventory-validation")
    parser.add_argument("--require-content-inventory", action="store_true")
    parser.add_argument("--chart-manifest-validation")
    parser.add_argument("--require-chart-manifest", action="store_true")
    parser.add_argument("--asset-hash-validation")
    parser.add_argument("--require-asset-hashes", action="store_true")
    parser.add_argument("--multipage-layout-validation")
    parser.add_argument("--require-multipage-layout", action="store_true")
    parser.add_argument("--preview-consistency-validation")
    parser.add_argument("--require-preview-consistency", action="store_true")
    parser.add_argument("--route-validation")
    parser.add_argument("--require-route", action="store_true")
    parser.add_argument("--manifest-validation")
    parser.add_argument("--require-editability", action="store_true")
    parser.add_argument("--semantic-object-audit")
    parser.add_argument("--object-manifest")
    parser.add_argument("--require-semantic-object-audit", action="store_true")
    parser.add_argument("--project-report")
    parser.add_argument("--require-project-report", action="store_true")
    parser.add_argument("--expected-ratio", type=float)
    parser.add_argument("--report")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    issues = []
    if not project.is_dir():
        result = {"schema": "ai-ppt-plus/project-validation/v1", "valid": False, "issues": [{"severity": "blocker", "code": "project_missing", "path": str(project)}]}
        print(json.dumps(result, ensure_ascii=False))
        return 3

    handoff_path = project / "handoff.json"
    manifest_path = project / "slide-manifest.json"
    asset_manifest_path = project / "asset-manifest.json"
    validation_path = project / "validation-report.json"
    issue_log_path = project / "issue-log.json"
    handoff = read_json(handoff_path, issues, "handoff")
    manifest = read_json(manifest_path, issues, "slide-manifest")
    validation = read_json(validation_path, issues, "validation-report")
    issue_log = read_json(issue_log_path, issues, "issue-log")
    assets = read_json(asset_manifest_path, issues, "asset-manifest") if asset_manifest_path.exists() else {"assets": []}
    deck = Path(args.deck).resolve()
    if not deck.is_file():
        issues.append({"severity": "blocker", "code": "deck_missing", "path": str(deck)})
    current_hash = sha256(deck) if deck.is_file() else None

    inspection_path = Path(args.inspection).resolve() if args.inspection else project / "inspection.json"
    render_path = Path(args.render_report).resolve() if args.render_report else project / "render-report.json"
    inspection = read_json(inspection_path, issues, "inspection")
    render = read_json(render_path, issues, "render-report")

    quality_evidence = {}

    def read_quality_report(argument, label):
        if not argument:
            return None
        report = read_json(Path(argument).resolve(), issues, label)
        if report is not None and report.get("valid") is not True:
            issues.append({"severity": "blocker", "code": "quality_report_failed", "artifact": label, "report_issues": report.get("issues", [])})
        return report

    render_gate = read_quality_report(args.render_visual_gate, "render-visual-gate")
    visual_comparison = read_quality_report(args.visual_comparison, "visual-comparison")
    ocr_report = read_quality_report(args.ocr_report, "ocr-text-check")
    content_inventory_report = read_quality_report(args.content_inventory_validation, "content-inventory-validation")
    chart_manifest_report = read_quality_report(args.chart_manifest_validation, "chart-manifest-validation")
    asset_hash_report = read_quality_report(args.asset_hash_validation, "asset-hash-validation")
    multipage_layout_report = read_quality_report(args.multipage_layout_validation, "multipage-layout-validation")
    preview_consistency_report = read_quality_report(args.preview_consistency_validation, "preview-consistency-validation")
    route_report = read_quality_report(args.route_validation, "route-validation")
    manifest_report = read_quality_report(args.manifest_validation, "manifest-validation")
    semantic_report = read_quality_report(args.semantic_object_audit, "semantic-object-audit")
    project_report = read_quality_report(args.project_report, "project-report")
    if args.require_route and route_report is None:
        issues.append({"severity": "blocker", "code": "route_validation_missing", "artifact": "route-validation"})
    if args.require_content_inventory and content_inventory_report is None:
        issues.append({"severity": "blocker", "code": "content_inventory_missing", "artifact": "content-inventory-validation"})
    if args.require_chart_manifest and chart_manifest_report is None:
        issues.append({"severity": "blocker", "code": "chart_manifest_missing", "artifact": "chart-manifest-validation"})
    if args.require_asset_hashes and asset_hash_report is None:
        issues.append({"severity": "blocker", "code": "asset_hash_validation_missing", "artifact": "asset-hash-validation"})
    if args.require_multipage_layout and multipage_layout_report is None:
        issues.append({"severity": "blocker", "code": "multipage_layout_validation_missing", "artifact": "multipage-layout-validation"})
    if args.require_preview_consistency and preview_consistency_report is None:
        issues.append({"severity": "blocker", "code": "preview_consistency_validation_missing", "artifact": "preview-consistency-validation"})
    if args.require_editability and manifest_report is None:
        issues.append({"severity": "blocker", "code": "manifest_validation_missing", "artifact": "manifest-validation"})
    object_manifest_path = Path(args.object_manifest).resolve() if args.object_manifest else project / "slide-object-manifest.json"
    object_manifest = read_json(object_manifest_path, issues, "slide-object-manifest") if args.require_semantic_object_audit or object_manifest_path.is_file() else None
    if args.require_semantic_object_audit and semantic_report is None:
        issues.append({"severity": "blocker", "code": "semantic_object_audit_missing", "artifact": "semantic-object-audit"})
    if args.require_project_report and project_report is None:
        issues.append({"severity": "blocker", "code": "project_report_missing", "artifact": "project-report"})
    if render_gate is not None:
        quality_evidence["render_visual_gate"] = {
            "valid": render_gate.get("valid"),
            "expected_pages": render_gate.get("expected_pages"),
            "observed_pages": len(render_gate.get("pages", [])),
            "issues": render_gate.get("issues", []),
        }
    if visual_comparison is not None:
        quality_evidence["visual_comparison"] = {
            "valid": visual_comparison.get("valid"),
            "reference": visual_comparison.get("reference"),
            "metrics": visual_comparison.get("metrics", {}),
            "issues": visual_comparison.get("issues", []),
            "human_visual_review_required": visual_comparison.get("human_visual_review_required", True),
        }
    if ocr_report is not None:
        quality_evidence["ocr_text_check"] = {
            "valid": ocr_report.get("valid"),
            "status": ocr_report.get("status"),
            "language": ocr_report.get("language"),
            "slide_count": len(ocr_report.get("slides", [])),
            "issues": ocr_report.get("issues", []),
        }
    if content_inventory_report is not None:
        quality_evidence["content_inventory_validation"] = {
            "valid": content_inventory_report.get("valid"),
            "status": content_inventory_report.get("status"),
            "visible_text_count": content_inventory_report.get("visible_text_count"),
            "chart_count": content_inventory_report.get("chart_count"),
            "chart_annotation_count": content_inventory_report.get("chart_annotation_count"),
            "issues": content_inventory_report.get("errors", content_inventory_report.get("issues", [])),
        }
    if chart_manifest_report is not None:
        quality_evidence["chart_manifest_validation"] = {
            "valid": chart_manifest_report.get("valid"),
            "status": chart_manifest_report.get("status"),
            "chart_count": chart_manifest_report.get("chart_count"),
            "charts": chart_manifest_report.get("charts", []),
            "issues": chart_manifest_report.get("errors", chart_manifest_report.get("issues", [])),
            "warnings": chart_manifest_report.get("warnings", []),
        }
    if asset_hash_report is not None:
        quality_evidence["asset_hash_validation"] = {
            "valid": asset_hash_report.get("valid"),
            "status": asset_hash_report.get("status"),
            "strict": asset_hash_report.get("strict"),
            "record_count": asset_hash_report.get("record_count"),
            "checked_count": asset_hash_report.get("checked_count"),
            "issues": asset_hash_report.get("issues", []),
            "warnings": asset_hash_report.get("warnings", []),
        }
    if multipage_layout_report is not None:
        quality_evidence["multipage_layout_validation"] = {
            "valid": multipage_layout_report.get("valid"),
            "status": multipage_layout_report.get("status"),
            "expected_pages": multipage_layout_report.get("expected_pages"),
            "selected_pages": multipage_layout_report.get("selected_pages"),
            "issues": multipage_layout_report.get("issues", []),
            "warnings": multipage_layout_report.get("warnings", []),
        }
    if preview_consistency_report is not None:
        quality_evidence["preview_consistency_validation"] = {
            "valid": preview_consistency_report.get("valid"),
            "status": preview_consistency_report.get("status"),
            "aggregate": preview_consistency_report.get("aggregate", {}),
            "threshold": preview_consistency_report.get("threshold"),
            "issues": preview_consistency_report.get("issues", []),
            "warnings": preview_consistency_report.get("warnings", []),
        }
    if route_report is not None:
        quality_evidence["route_validation"] = {
            "valid": route_report.get("valid"),
            "route": route_report.get("route"),
            "visual_authority": route_report.get("visual_authority"),
            "formal_content_authority": route_report.get("formal_content_authority"),
            "issues": route_report.get("issues", []),
        }
    if manifest_report is not None:
        quality_evidence["manifest_validation"] = {
            "valid": manifest_report.get("valid"),
            "issues": manifest_report.get("issues", []),
            "warnings": manifest_report.get("warnings", []),
            "editability": manifest_report.get("editability", []),
        }
        if manifest_report.get("manifest_sha256") and manifest_path.is_file() and manifest_report.get("manifest_sha256") != sha256(manifest_path):
            issues.append({"severity": "blocker", "code": "stale_manifest_validation", "expected": sha256(manifest_path), "observed": manifest_report.get("manifest_sha256")})
    if route_report is not None:
        route_file = Path(route_report.get("route_file", ""))
        if route_report.get("route_sha256") and (not route_file.is_file() or route_report.get("route_sha256") != sha256(route_file)):
            issues.append({"severity": "blocker", "code": "stale_route_validation", "artifact": "route-validation"})
        for reference in (route_report.get("evidence") or {}).get("reference_files", []):
            reference_path = Path(reference.get("path", ""))
            if reference.get("sha256") and (not reference_path.is_file() or reference.get("sha256") != sha256(reference_path)):
                issues.append({"severity": "blocker", "code": "stale_reference_validation", "slide_no": reference.get("slide_no")})
    if project_report is not None:
        quality_evidence["project_report"] = {
            "valid": project_report.get("valid"),
            "status": project_report.get("status"),
            "reports_total": project_report.get("reports_total"),
            "issues": project_report.get("issues", []),
        }
        if project_report.get("deck_sha256") and project_report.get("deck_sha256") != current_hash:
            issues.append({"severity": "blocker", "code": "stale_project_report"})
        report_index = Path(project_report.get("report_index_path", ""))
        if project_report.get("report_index_sha256") and (not report_index.is_file() or project_report.get("report_index_sha256") != sha256(report_index)):
            issues.append({"severity": "blocker", "code": "stale_report_index"})
        for child in (project_report.get("evidence") or {}).get("reports", []):
            child_path = Path(child.get("path", ""))
            if child.get("sha256") and (not child_path.is_file() or child.get("sha256") != sha256(child_path)):
                issues.append({"severity": "blocker", "code": "stale_child_report", "report_type": child.get("report_type")})

    if handoff:
        approved = handoff.get("approved_artifacts") or {}
        expected_hash = approved.get("pptx_sha256")
        if expected_hash and deck.is_file():
            observed_hash = sha256(deck)
            if observed_hash != expected_hash:
                issues.append({"severity": "blocker", "code": "handoff_hash_mismatch", "expected": expected_hash, "observed": observed_hash})
        if handoff.get("current_stage") == "delivered" and handoff.get("open_blockers"):
            issues.append({"severity": "blocker", "code": "delivered_with_open_blockers"})
        if handoff.get("current_stage") == "delivered" and handoff.get("remaining_slides"):
            issues.append({"severity": "blocker", "code": "delivered_with_remaining_slides"})

    if manifest and handoff:
        if manifest.get("state") and handoff.get("current_stage") and manifest.get("state") != handoff.get("current_stage"):
            issues.append({"severity": "blocker", "code": "state_mismatch", "handoff": handoff.get("current_stage"), "manifest": manifest.get("state")})
        slides = manifest.get("slides") or []
        if not isinstance(slides, list) or not slides:
            issues.append({"severity": "blocker", "code": "manifest_without_slides"})

    for report, label in ((inspection, "inspection"), (render, "render-report")):
        if report:
            report_hash = report.get("deck_sha256")
            if not report_hash:
                issues.append({"severity": "blocker", "code": "report_missing_deck_hash", "artifact": label})
            elif report_hash != current_hash:
                issues.append({"severity": "blocker", "code": "stale_report", "artifact": label, "expected": current_hash, "observed": report_hash})

    if inspection and manifest:
        observed_slides = inspection.get("slide_count")
        declared_slides = manifest.get("slide_count")
        if declared_slides is None:
            declared_slides = len(manifest.get("slides") or [])
        if observed_slides != declared_slides:
            issues.append({"severity": "blocker", "code": "slide_count_mismatch", "inspection": observed_slides, "manifest": declared_slides})
        if args.expected_ratio is not None:
            observed_ratio = inspection.get("ratio")
            if observed_ratio is None or abs(observed_ratio - args.expected_ratio) >= 0.01:
                issues.append({"severity": "blocker", "code": "ratio_mismatch", "expected": args.expected_ratio, "observed": observed_ratio})

    if validation and handoff and validation.get("status") and handoff.get("current_stage"):
        if validation.get("status") != handoff.get("current_stage"):
            issues.append({"severity": "blocker", "code": "validation_state_mismatch", "validation": validation.get("status"), "handoff": handoff.get("current_stage")})

    if issue_log:
        open_critical = [item for item in issue_log.get("issues", []) if item.get("severity") in {"blocker", "critical"} and item.get("status", "open") not in {"closed", "fixed", "accepted"}]
        if open_critical:
            issues.append({"severity": "blocker", "code": "open_critical_issues", "count": len(open_critical)})

    editability_evidence = []
    if manifest:
        for slide in manifest.get("slides") or []:
            objects = slide.get("objects")
            slide_no = slide.get("slide_no")
            if not isinstance(objects, list):
                editability_evidence.append({"slide_no": slide_no, "status": "legacy-untyped"})
                if args.require_editability:
                    issues.append({"severity": "blocker", "code": "editability_levels_missing", "slide_no": slide_no})
                continue
            object_issues = validate_objects(objects)
            summary = summarize_objects(objects)
            editability_evidence.append({"slide_no": slide_no, "status": "typed", "summary": summary, "issues": object_issues})
            for item in object_issues:
                if item.get("severity") == "blocker":
                    issues.append({**item, "severity": "blocker", "code": item.get("code"), "slide_no": slide_no})
            if summary.get("formal_content_rasterized"):
                issues.append({"severity": "blocker", "code": "formal_content_rasterized", "slide_no": slide_no})
        quality_evidence["editability"] = {"protocol": "L0-L5/v1", "slides": editability_evidence}

    if semantic_report is not None:
        quality_evidence["semantic_object_audit"] = {
            "valid": semantic_report.get("valid"),
            "status": semantic_report.get("status"),
            "audited_object_count": semantic_report.get("audited_object_count"),
            "errors": semantic_report.get("errors", []),
            "warnings": semantic_report.get("warnings", []),
        }
        if object_manifest is not None:
            expected_object_count = sum(
                len(slide.get("objects", []))
                for slide in (object_manifest.get("slides") or [])
                if isinstance(slide, dict) and isinstance(slide.get("objects"), list)
            )
            if semantic_report.get("object_manifest_sha256") and semantic_report.get("object_manifest_sha256") != sha256(object_manifest_path):
                issues.append({"severity": "blocker", "code": "stale_semantic_object_audit", "expected": sha256(object_manifest_path), "observed": semantic_report.get("object_manifest_sha256")})
            if semantic_report.get("audited_object_count") != expected_object_count:
                issues.append({"severity": "blocker", "code": "semantic_object_count_mismatch", "expected": expected_object_count, "observed": semantic_report.get("audited_object_count")})

    quality_degradations = []
    if ocr_report is not None and ocr_report.get("status") == "unavailable":
        quality_degradations.append({"code": "ocr_unavailable", "language": ocr_report.get("language"), "requires_human_review": True})

    result = {
        "schema": "ai-ppt-plus/project-validation/v1",
        "valid": not any(item["severity"] == "blocker" for item in issues),
        "project_dir": str(project),
        "deck": str(deck),
        "deck_sha256": current_hash,
        "state": (handoff or {}).get("current_stage"),
        "asset_count": len((assets or {}).get("assets") or []),
        "editability": quality_evidence.get("editability", {}).get("slides", []),
        "project_report": {"valid": project_report.get("valid"), "status": project_report.get("status")} if project_report else None,
        "quality_evidence": quality_evidence,
        "quality_degradations": quality_degradations,
        "issues": issues,
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
