#!/usr/bin/env python3
"""Combine artifact, quality, route, editability and human sign-off gates."""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from atomic_output import atomic_write_json
from editability import summarize_objects, validate_objects


def load(path):
    if not path or not Path(path).exists():
        return None
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx")
    parser.add_argument("--inspection", required=True)
    parser.add_argument("--render-report", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--handoff")
    parser.add_argument("--issue-log")
    parser.add_argument("--asset-manifest")
    parser.add_argument("--human-signoff")
    parser.add_argument("--signoff-report")
    parser.add_argument("--route-validation")
    parser.add_argument("--require-route", action="store_true")
    parser.add_argument("--object-manifest")
    parser.add_argument("--semantic-object-audit")
    parser.add_argument("--require-semantic-object-audit", action="store_true")
    parser.add_argument("--manifest-registry-validation")
    parser.add_argument("--require-manifest-registry", action="store_true")
    parser.add_argument("--source-image-validation")
    parser.add_argument("--require-source-image-validation", action="store_true")
    parser.add_argument("--reference-audit")
    parser.add_argument("--require-reference-audit", action="store_true")
    parser.add_argument("--gradient-visual-validation")
    parser.add_argument("--require-gradient-visual", action="store_true")
    parser.add_argument("--icon-assets-validation")
    parser.add_argument("--require-icon-assets", action="store_true")
    parser.add_argument("--imagegen-assets-validation")
    parser.add_argument("--require-imagegen-assets", action="store_true")
    parser.add_argument("--panel-assets-validation")
    parser.add_argument("--require-panel-assets", action="store_true")
    parser.add_argument("--text-layout-validation")
    parser.add_argument("--require-text-model", action="store_true")
    parser.add_argument("--text-style-map-validation")
    parser.add_argument("--require-text-style-map", action="store_true")
    parser.add_argument("--manifest-validation")
    parser.add_argument("--require-editability", action="store_true")
    parser.add_argument("--require-embedded-fonts", action="store_true", help="block delivery unless the inspection report detects OOXML embedded fonts")
    parser.add_argument("--project-report")
    parser.add_argument("--require-project-report", action="store_true")
    parser.add_argument("--report-bundle-validation")
    parser.add_argument("--require-report-bundle", action="store_true")
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
    parser.add_argument("--font-delivery-report")
    parser.add_argument("--require-font-delivery", action="store_true")
    parser.add_argument("--expected-slides", type=int)
    parser.add_argument("--expected-ratio", type=float)
    parser.add_argument("--quality-score", type=float)
    parser.add_argument("--quality-threshold", type=float, default=80)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    inspection = load(args.inspection)
    render = load(args.render_report)
    manifest = load(args.manifest)
    issue_log = load(args.issue_log) or {"issues": []}
    assets = load(args.asset_manifest) or {"assets": []}
    sign = load(args.human_signoff) or {}
    signoff_report = load(args.signoff_report) if args.signoff_report else None
    route_report = load(args.route_validation) if args.route_validation else None
    manifest_report = load(args.manifest_validation) if args.manifest_validation else None
    semantic_report = load(args.semantic_object_audit) if args.semantic_object_audit else None
    registry_report = load(args.manifest_registry_validation) if args.manifest_registry_validation else None
    source_image_report = load(args.source_image_validation) if args.source_image_validation else None
    reference_audit_report = load(args.reference_audit) if args.reference_audit else None
    gradient_report = load(args.gradient_visual_validation) if args.gradient_visual_validation else None
    icon_report = load(args.icon_assets_validation) if args.icon_assets_validation else None
    imagegen_report = load(args.imagegen_assets_validation) if args.imagegen_assets_validation else None
    panel_report = load(args.panel_assets_validation) if args.panel_assets_validation else None
    text_model_report = load(args.text_layout_validation) if args.text_layout_validation else None
    text_style_report = load(args.text_style_map_validation) if args.text_style_map_validation else None
    content_inventory_report = load(args.content_inventory_validation) if args.content_inventory_validation else None
    chart_manifest_report = load(args.chart_manifest_validation) if args.chart_manifest_validation else None
    asset_hash_report = load(args.asset_hash_validation) if args.asset_hash_validation else None
    multipage_layout_report = load(args.multipage_layout_validation) if args.multipage_layout_validation else None
    preview_consistency_report = load(args.preview_consistency_validation) if args.preview_consistency_validation else None
    project_report = load(args.project_report) if args.project_report else None
    report_bundle = load(args.report_bundle_validation) if args.report_bundle_validation else None
    font_delivery = load(args.font_delivery_report) if args.font_delivery_report else None
    handoff = load(args.handoff) if args.handoff else None
    manifest_slides = (manifest or {}).get("slides") or []
    asset_items = (assets or {}).get("assets") or []
    blocking = []
    passed = []
    quality_evidence = {}
    quality_degradations = []
    editability_evidence = []

    def check(ok, code, detail, slide=None):
        (passed if ok else blocking).append({"type": code, "severity": "passed" if ok else "blocking", "slide": slide, "detail": detail})

    pptx_path = Path(args.pptx)
    check(pptx_path.exists() and zipfile.is_zipfile(pptx_path), "invalid_or_missing_pptx", "PPTX must exist and be an OOXML zip package")
    check(bool(inspection and inspection.get("ok")), "structural_inspection_failed", "inspection report must be present and pass")
    check(bool(render and render.get("ok")), "render_failed", "render report must be present and pass")
    current_hash = sha256(args.pptx) if pptx_path.is_file() else None
    check(not inspection or not inspection.get("deck_sha256") or inspection.get("deck_sha256") == current_hash, "stale_inspection_report", "inspection report must describe the current PPTX")
    check(not render or not render.get("deck_sha256") or render.get("deck_sha256") == current_hash, "stale_render_report", "render report must describe the current PPTX")
    if args.require_embedded_fonts:
        check(bool((inspection or {}).get("embedded_fonts", {}).get("present")), "embedded_fonts_missing", "Chinese delivery requires verified OOXML embedded font parts")
    if args.require_font_delivery:
        if font_delivery and font_delivery.get("valid") is True:
            passed.append({"type": "font_delivery_validation_passed", "severity": "passed", "slide": None, "detail": "font declaration, resolution and final-render evidence passed"})
        else:
            blocking.append({"type": "font_delivery_validation_failed", "severity": "blocking", "slide": None, "detail": "font declaration, resolution and final-render evidence must pass", "report_issues": (font_delivery or {}).get("issues", [])})
    if font_delivery:
        quality_evidence["font_delivery"] = {"valid": font_delivery.get("valid"), "status": font_delivery.get("status"), "profile": font_delivery.get("profile"), "declared_font": font_delivery.get("declared_font"), "resolved_font": font_delivery.get("resolved_font"), "render_visible": font_delivery.get("render_visible"), "embedded_font": font_delivery.get("embedded_font"), "issues": font_delivery.get("issues", [])}

    if args.require_route:
        check(bool(route_report and route_report.get("valid") is True), "route_validation_failed", "a valid route-validation report is required")
    elif route_report:
        check(route_report.get("valid") is True, "route_validation_failed", "route-validation report must be valid")
    if route_report:
        quality_evidence["route_validation"] = {"valid": route_report.get("valid"), "route": route_report.get("route"), "visual_authority": route_report.get("visual_authority"), "formal_content_authority": route_report.get("formal_content_authority"), "issues": route_report.get("issues", [])}
        route_file = Path(route_report.get("route_file", ""))
        check(not route_report.get("route_sha256") or (route_file.is_file() and sha256(route_file) == route_report.get("route_sha256")), "stale_route_validation", "route-validation report must describe the current route decision")
        for reference in (route_report.get("evidence") or {}).get("reference_files", []):
            reference_path = Path(reference.get("path", ""))
            check(not reference.get("sha256") or (reference_path.is_file() and sha256(reference_path) == reference.get("sha256")), "stale_reference_validation", "route reference hash must match the current reference file", reference.get("slide_no"))

    def required_quality(report, required: bool, code: str, label: str):
        if required:
            check(bool(report and report.get("valid") is True), code, f"{label} report must be present and valid")
        elif report:
            check(report.get("valid") is True, code, f"{label} report must be valid")

    required_quality(semantic_report, args.require_semantic_object_audit, "semantic_object_audit_failed", "semantic object audit")
    required_quality(registry_report, args.require_manifest_registry, "manifest_registry_failed", "manifest registry")
    required_quality(source_image_report, args.require_source_image_validation, "source_image_validation_failed", "source image validation")
    required_quality(reference_audit_report, args.require_reference_audit, "reference_audit_failed", "reference audit")
    required_quality(gradient_report, args.require_gradient_visual, "gradient_visual_validation_failed", "gradient visual validation")
    required_quality(icon_report, args.require_icon_assets, "icon_assets_validation_failed", "icon asset validation")
    required_quality(imagegen_report, args.require_imagegen_assets, "imagegen_assets_validation_failed", "imagegen asset validation")
    required_quality(panel_report, args.require_panel_assets, "panel_assets_validation_failed", "panel asset validation")
    required_quality(text_model_report, args.require_text_model, "text_model_validation_failed", "text model validation")
    required_quality(text_style_report, args.require_text_style_map, "text_style_map_validation_failed", "text style map validation")
    required_quality(content_inventory_report, args.require_content_inventory, "content_inventory_validation_failed", "visible-content inventory")
    required_quality(chart_manifest_report, args.require_chart_manifest, "chart_manifest_validation_failed", "chart manifest")
    required_quality(asset_hash_report, args.require_asset_hashes, "asset_hash_validation_failed", "asset hash validation")
    required_quality(multipage_layout_report, args.require_multipage_layout, "multipage_layout_validation_failed", "multi-page layout validation")
    required_quality(preview_consistency_report, args.require_preview_consistency, "preview_consistency_validation_failed", "preview/final-render consistency")
    if asset_hash_report:
        quality_evidence["asset_hash_validation"] = {
            "valid": asset_hash_report.get("valid"),
            "status": asset_hash_report.get("status"),
            "strict": asset_hash_report.get("strict"),
            "record_count": asset_hash_report.get("record_count"),
            "checked_count": asset_hash_report.get("checked_count"),
            "issues": asset_hash_report.get("issues", []),
            "warnings": asset_hash_report.get("warnings", []),
        }
    if chart_manifest_report:
        quality_evidence["chart_manifest_validation"] = {
            "valid": chart_manifest_report.get("valid"),
            "status": chart_manifest_report.get("status"),
            "chart_count": chart_manifest_report.get("chart_count"),
            "charts": chart_manifest_report.get("charts", []),
            "issues": chart_manifest_report.get("errors", chart_manifest_report.get("issues", [])),
            "warnings": chart_manifest_report.get("warnings", []),
        }
    if multipage_layout_report:
        quality_evidence["multipage_layout_validation"] = {
            "valid": multipage_layout_report.get("valid"),
            "status": multipage_layout_report.get("status"),
            "expected_pages": multipage_layout_report.get("expected_pages"),
            "selected_pages": multipage_layout_report.get("selected_pages"),
            "issues": multipage_layout_report.get("issues", []),
            "warnings": multipage_layout_report.get("warnings", []),
        }
    if preview_consistency_report:
        quality_evidence["preview_consistency_validation"] = {
            "valid": preview_consistency_report.get("valid"),
            "status": preview_consistency_report.get("status"),
            "aggregate": preview_consistency_report.get("aggregate", {}),
            "threshold": preview_consistency_report.get("threshold"),
            "issues": preview_consistency_report.get("issues", []),
            "warnings": preview_consistency_report.get("warnings", []),
        }
    if args.require_semantic_object_audit and args.object_manifest:
        object_path = Path(args.object_manifest)
        object_data = load(args.object_manifest)
        expected_objects = sum(
            len(slide.get("objects", []))
            for slide in (object_data or {}).get("slides", []) or []
            if isinstance(slide, dict) and isinstance(slide.get("objects"), list)
        )
        if semantic_report:
            check(semantic_report.get("object_manifest_sha256") == sha256(object_path), "stale_semantic_object_audit", "semantic audit must describe the current object manifest")
            check(semantic_report.get("audited_object_count") == expected_objects, "semantic_object_count_mismatch", "semantic audit must cover every manifest object")

    if args.manifest_validation:
        check(bool(manifest_report and manifest_report.get("valid") is True), "manifest_validation_failed", "manifest-validation report must be present and valid")
        if manifest_report:
            quality_evidence["manifest_validation"] = {"valid": manifest_report.get("valid"), "issues": manifest_report.get("issues", []), "warnings": manifest_report.get("warnings", []), "editability": manifest_report.get("editability", [])}
            manifest_path = Path(args.manifest)
            check(not manifest_report.get("manifest_sha256") or (manifest_path.is_file() and sha256(manifest_path) == manifest_report.get("manifest_sha256")), "stale_manifest_validation", "manifest-validation report must describe the current manifest")
    elif args.require_editability:
        check(False, "manifest_validation_missing", "--require-editability requires a manifest-validation report")
    if args.require_project_report:
        check(bool(project_report and project_report.get("valid") is True), "project_report_missing_or_failed", "a valid project-report.json is required")
    elif project_report:
        check(project_report.get("valid") is True, "project_report_failed", "project-report.json must be valid")
    if project_report:
        quality_evidence["project_report"] = {"valid": project_report.get("valid"), "status": project_report.get("status"), "reports_total": project_report.get("reports_total"), "issues": project_report.get("issues", [])}
        check(not project_report.get("deck_sha256") or project_report.get("deck_sha256") == current_hash, "stale_project_report", "project report must describe the current PPTX")
        index_path = Path(project_report.get("report_index_path", ""))
        check(not project_report.get("report_index_sha256") or (index_path.is_file() and sha256(index_path) == project_report.get("report_index_sha256")), "stale_report_index", "project report must describe the current report index")
        for child in (project_report.get("evidence") or {}).get("reports", []):
            child_path = Path(child.get("path", ""))
            check(not child.get("sha256") or (child_path.is_file() and sha256(child_path) == child.get("sha256")), "stale_child_report", "project aggregate child report changed after aggregation", child.get("report_type"))
    if args.require_report_bundle:
        check(bool(report_bundle and report_bundle.get("valid") is True), "report_bundle_missing_or_failed", "a fresh and consistent report-bundle-validation.json is required")
    elif report_bundle:
        check(report_bundle.get("valid") is True, "report_bundle_failed", "report-bundle-validation.json must be valid")
    if report_bundle:
        quality_evidence["report_bundle_validation"] = {
            "valid": report_bundle.get("valid"),
            "status": report_bundle.get("status"),
            "validation_scope": report_bundle.get("validation_scope"),
            "checks": report_bundle.get("checks", []),
            "issues": report_bundle.get("issues", []),
        }
        check(not report_bundle.get("deck_sha256") or report_bundle.get("deck_sha256") == current_hash, "stale_report_bundle_deck", "report-bundle validation must describe the current PPTX")
        bundle_index_path = Path(report_bundle.get("report_index_path", ""))
        check(not report_bundle.get("report_index_sha256") or (bundle_index_path.is_file() and sha256(bundle_index_path) == report_bundle.get("report_index_sha256")), "stale_report_bundle_index", "report-bundle validation must describe the current report index")
        bundle_pipeline_path = Path(report_bundle.get("pipeline_result_path", ""))
        check(not report_bundle.get("pipeline_result_sha256") or (bundle_pipeline_path.is_file() and sha256(bundle_pipeline_path) == report_bundle.get("pipeline_result_sha256")), "stale_report_bundle_pipeline", "report-bundle validation must describe the current pipeline result")
        bundle_review_path = Path(report_bundle.get("review_html_path", "")) if report_bundle.get("review_html_path") else None
        check(not report_bundle.get("review_html_sha256") or (bundle_review_path is not None and bundle_review_path.is_file() and sha256(bundle_review_path) == report_bundle.get("review_html_sha256")), "stale_report_bundle_review", "report-bundle validation must describe the current review HTML")

    for option, label in ((args.render_visual_gate, "render-visual-gate"), (args.visual_comparison, "visual-comparison"), (args.ocr_report, "ocr-text-check")):
        report = load(option) if option else None
        if option:
            if report and report.get("valid") is True:
                passed.append({"type": "quality_report_valid", "severity": "passed", "slide": None, "detail": f"{label} report is present and valid"})
            else:
                blocking.append({"type": "quality_report_failed", "severity": "blocking", "slide": None, "detail": f"{label} report must be present and valid", "report_issues": (report or {}).get("issues", [])})
            if report is not None:
                quality_evidence[label.replace("-", "_")] = {"valid": report.get("valid"), "status": report.get("status"), "language": report.get("language"), "metrics": report.get("metrics", {}), "issues": report.get("issues", [])}
                if label == "ocr-text-check" and report.get("status") == "unavailable":
                    quality_degradations.append({"code": "ocr_unavailable", "language": report.get("language"), "requires_human_review": True})

    if args.signoff_report:
        if signoff_report and signoff_report.get("valid") is True:
            passed.append({"type": "human_signoff_validation_passed", "severity": "passed", "slide": None, "detail": "sign-off report is present and valid"})
        else:
            blocking.append({"type": "human_signoff_validation_failed", "severity": "blocking", "slide": None, "detail": "sign-off report must be present and valid", "report_issues": (signoff_report or {}).get("issues", [])})
        if not sign and signoff_report and signoff_report.get("valid") is True:
            sign = signoff_report.get("decisions") or {}
    if args.handoff:
        approved = (handoff or {}).get("approved_artifacts") or {}
        check(bool(handoff and handoff.get("project_id")), "handoff_missing", "handoff report must be present and valid")
        check(not approved.get("pptx_sha256") or approved.get("pptx_sha256") == current_hash, "handoff_hash_mismatch", "handoff approved PPTX hash must match the current PPTX")
        check(not handoff or not manifest or not manifest.get("state") or not handoff.get("current_stage") or manifest.get("state") == handoff.get("current_stage"), "state_mismatch", "handoff state and slide manifest state must agree")

    if args.expected_slides is not None:
        check(bool(inspection and inspection.get("slide_count") == args.expected_slides), "slide_count_mismatch", f"expected {args.expected_slides}, observed {(inspection or {}).get('slide_count')}")
    if args.expected_ratio is not None:
        ratio_ok = bool(inspection and inspection.get("is_16_9")) if abs(args.expected_ratio - 16 / 9) < 0.01 else bool(inspection and inspection.get("ratio") is not None and abs(inspection.get("ratio") - args.expected_ratio) < 0.01)
        check(ratio_ok, "ratio_mismatch", f"expected {args.expected_ratio}, observed {(inspection or {}).get('ratio')}")
    check(not (render and inspection and len(render.get("pages", [])) != inspection.get("slide_count")), "render_count_mismatch", "rendered page count must match inspected slide count")
    check(bool(manifest and len(manifest_slides) == (inspection or {}).get("slide_count")), "manifest_slide_count_mismatch", "manifest page count must match inspected slide count")
    bad_sources = [item.get("slide_no") for item in manifest_slides if not item.get("formal_content_source")]
    check(not bad_sources, "untraceable_formal_content", "formal content source required", bad_sources or None)
    undocumented = [item for item in manifest_slides if item.get("asset_status") == "placeholder" and not item.get("placeholder_reason")]
    check(not undocumented, "undocumented_placeholders", "placeholder must contain a reason", [item.get("slide_no") for item in undocumented] or None)
    check(not any(not item.get("provenance") for item in asset_items), "asset_provenance_missing", "every asset needs provenance")

    editability_blockers = []
    for slide in manifest_slides:
        slide_no = slide.get("slide_no")
        objects = slide.get("objects")
        if not isinstance(objects, list):
            if args.require_editability:
                editability_blockers.append({"severity": "blocker", "code": "editability_levels_missing", "slide_no": slide_no})
                editability_evidence.append({"slide_no": slide_no, "status": "missing"})
            else:
                editability_evidence.append({"slide_no": slide_no, "status": "legacy-untyped"})
            continue
        object_issues = validate_objects(objects)
        summary = summarize_objects(objects)
        editability_evidence.append({"slide_no": slide_no, "status": "typed", "summary": summary, "issues": object_issues})
        for issue in object_issues:
            if issue.get("severity") == "blocker" or issue.get("code") in {"l2_human_review_not_recorded", "l3_human_review_not_recorded", "human_review_required_missing"}:
                editability_blockers.append({**issue, "slide_no": slide_no})
        if summary["formal_content_rasterized"]:
            editability_blockers.append({"severity": "blocker", "code": "formal_content_rasterized", "slide_no": slide_no})
        if summary["delivery_decision"] in {"blocked", "manual-required"} and any(obj.get("required_for_delivery") is True for obj in objects if isinstance(obj, dict)):
            editability_blockers.append({"severity": "blocker", "code": "editability_delivery_decision_blocked", "slide_no": slide_no, "decision": summary["delivery_decision"]})
    if editability_blockers:
        blocking.extend({"type": item["code"], "severity": "blocking", "slide": item.get("slide_no"), "detail": item.get("message", item.get("code")), "evidence": item} for item in editability_blockers)
    if editability_evidence:
        quality_evidence["editability"] = {"protocol": "L0-L5/v1", "slides": editability_evidence, "human_review_required": any(item.get("summary", {}).get("human_review_required") for item in editability_evidence if item.get("summary"))}
    if args.require_editability:
        check(not any(item.get("status") != "typed" for item in editability_evidence), "editability_levels_missing", "every slide needs typed L0-L5 object records")

    check(args.quality_score is not None and args.quality_score >= args.quality_threshold, "quality_threshold_not_met", f"score={args.quality_score}, threshold={args.quality_threshold}")
    open_critical = [item for item in issue_log.get("issues", []) if item.get("severity") in {"blocker", "critical"} and item.get("status", "open") not in {"closed", "fixed", "accepted"}]
    check(not open_critical, "open_blocker_or_critical_issues", "all blocker/critical issues must be closed", [item.get("slide") for item in open_critical] or None)

    required = ["narrative", "facts", "visual", "fidelity", "brand"]
    missing_signoff = [field for field in required if sign.get(field) is not True]
    if missing_signoff:
        check(False, "human_signoff_incomplete", "human narrative/facts/visual/fidelity/brand sign-off required", missing_signoff)
    else:
        passed.append({"type": "human_signoff_complete", "severity": "passed", "slide": None, "detail": "narrative/facts/visual/fidelity/brand sign-off recorded"})
    editability_confirmation_needed = [item.get("slide_no") for item in manifest_slides if isinstance(item.get("objects"), list) and any(isinstance(obj, dict) and obj.get("editability_level") in {"L3", "L4"} for obj in item.get("objects", []))]
    if editability_confirmation_needed and sign.get("editability") is not True:
        check(False, "editability_signoff_incomplete", "L3/L4 objects require explicit editability acceptance", editability_confirmation_needed)
    else:
        if editability_confirmation_needed:
            passed.append({"type": "editability_signoff_complete", "severity": "passed", "slide": editability_confirmation_needed, "detail": "reduced editability/manual placeholders explicitly accepted"})

    only_human = bool(blocking) and all(item["type"] in {"human_signoff_incomplete", "human_signoff_validation_failed", "editability_signoff_incomplete"} for item in blocking)
    output = {
        "schema": "ai-ppt-plus/delivery-check/v3",
        "status": "passed" if not blocking else "pending_human_closeout" if only_human else "failed",
        "next_state": "delivered" if not blocking else "human-closeout" if only_human else "revision-required",
        "may_claim_complete": not blocking,
        "blocking_issues": blocking,
        "passed": len(passed),
        "failed": len(blocking),
        "checks_passed": passed,
        "open_critical": open_critical,
        "undocumented_placeholders": undocumented,
        "missing_human_signoff": missing_signoff,
        "quality": {"score": args.quality_score, "threshold": args.quality_threshold},
        "quality_evidence": quality_evidence,
        "editability": editability_evidence,
        "project_report": project_report,
        "quality_degradations": quality_degradations,
    }
    output_path = Path(args.output)
    atomic_write_json(output_path.resolve(), output)
    print(json.dumps(output, ensure_ascii=False))
    return 0 if not blocking else 2


if __name__ == "__main__":
    raise SystemExit(main())
