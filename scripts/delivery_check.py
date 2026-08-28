#!/usr/bin/env python3
"""Combine artifact, quality, route, editability and human sign-off gates."""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from editability import summarize_objects, validate_objects


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path and Path(path).exists() else None


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
    parser.add_argument("--manifest-validation")
    parser.add_argument("--require-editability", action="store_true")
    parser.add_argument("--require-embedded-fonts", action="store_true", help="block delivery unless the inspection report detects OOXML embedded fonts")
    parser.add_argument("--project-report")
    parser.add_argument("--require-project-report", action="store_true")
    parser.add_argument("--render-visual-gate")
    parser.add_argument("--visual-comparison")
    parser.add_argument("--ocr-report")
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
    project_report = load(args.project_report) if args.project_report else None
    font_delivery = load(args.font_delivery_report) if args.font_delivery_report else None
    handoff = load(args.handoff) if args.handoff else None
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
        quality_evidence["font_delivery"] = {"valid": font_delivery.get("valid"), "status": font_delivery.get("status"), "profile": font_delivery.get("profile"), "declared_font": font_delivery.get("declared_font"), "resolved_font": font_delivery.get("resolved_font"), "render_visible": font_delivery.get("render_visible"), "embedded_font": font_delivery.get("embedded_font"), "target_review": font_delivery.get("target_review"), "issues": font_delivery.get("issues", [])}

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
    check(bool(manifest and len(manifest.get("slides", [])) == (inspection or {}).get("slide_count")), "manifest_slide_count_mismatch", "manifest page count must match inspected slide count")
    bad_sources = [item.get("slide_no") for item in (manifest or {}).get("slides", []) if not item.get("formal_content_source")]
    check(not bad_sources, "untraceable_formal_content", "formal content source required", bad_sources or None)
    undocumented = [item for item in (manifest or {}).get("slides", []) if item.get("asset_status") == "placeholder" and not item.get("placeholder_reason")]
    check(not undocumented, "undocumented_placeholders", "placeholder must contain a reason", [item.get("slide_no") for item in undocumented] or None)
    check(not any(not item.get("provenance") for item in assets.get("assets", [])), "asset_provenance_missing", "every asset needs provenance")

    editability_blockers = []
    for slide in (manifest or {}).get("slides", []):
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
    editability_confirmation_needed = [item.get("slide_no") for item in (manifest or {}).get("slides", []) if isinstance(item.get("objects"), list) and any(isinstance(obj, dict) and obj.get("editability_level") in {"L3", "L4"} for obj in item.get("objects", []))]
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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))
    return 0 if not blocking else 2


if __name__ == "__main__":
    raise SystemExit(main())
