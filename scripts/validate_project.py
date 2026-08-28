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

from editability import summarize_objects, validate_objects


def read_json(path: Path, issues, label):
    if not path.is_file():
        issues.append({"severity": "blocker", "code": "missing_artifact", "artifact": label, "path": str(path)})
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
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
    parser.add_argument("--route-validation")
    parser.add_argument("--require-route", action="store_true")
    parser.add_argument("--manifest-validation")
    parser.add_argument("--require-editability", action="store_true")
    parser.add_argument("--semantic-object-audit")
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
    route_report = read_quality_report(args.route_validation, "route-validation")
    manifest_report = read_quality_report(args.manifest_validation, "manifest-validation")
    semantic_report = read_quality_report(args.semantic_object_audit, "semantic-object-audit")
    project_report = read_quality_report(args.project_report, "project-report")
    if args.require_route and route_report is None:
        issues.append({"severity": "blocker", "code": "route_validation_missing", "artifact": "route-validation"})
    if args.require_editability and manifest_report is None:
        issues.append({"severity": "blocker", "code": "manifest_validation_missing", "artifact": "manifest-validation"})
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
        slides = manifest.get("slides")
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
        declared_slides = manifest.get("slide_count", len(manifest.get("slides", [])))
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
        for slide in manifest.get("slides", []):
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
        "asset_count"…3001 tokens truncated…None, "all", []), "full_scope_pages", "full bundles must not masquerade as a page subset", observed=affected_pages)

    report_entries, entry_issues = _report_entry_paths(index, index_path)
    issues.extend(entry_issues)
    aggregate_evidence = (project_report.get("evidence") or {}).get("reports") if isinstance(project_report.get("evidence"), dict) else []
    if not isinstance(aggregate_evidence, list):
        issues.append({"severity": "blocker", "code": "aggregate_evidence_invalid", "message": "project aggregate evidence.reports must be an array"})
        aggregate_evidence = []
    evidence_by_type = {
        item.get("report_type"): item
        for item in aggregate_evidence
        if isinstance(item, dict) and isinstance(item.get("report_type"), str)
    }
    input_hashes = project_report.get("input_hashes") if isinstance(project_report.get("input_hashes"), dict) else {}
    for entry in report_entries:
        report_type = entry["report_type"]
        path = entry["resolved_path"]
        required = entry.get("required") is True
        present = path.is_file()
        check(present or not required, "child_report_present", f"indexed {'required' if required else 'optional'} child report must exist", report_type=report_type, path=str(path), required=required)
        evidence = evidence_by_type.get(report_type)
        check(evidence is not None, "child_evidence_present", "every indexed child report must appear in aggregate evidence", report_type=report_type)
        if not present:
            continue
        child_hash = sha256(path)
        if evidence:
            check(evidence.get("sha256") == child_hash, "child_hash_fresh", "aggregate child evidence must match the current child report", report_type=report_type, expected=child_hash, observed=evidence.get("sha256"))
            source = evidence.get("source") if isinstance(evidence.get("source"), dict) else {}
            check(source.get("sha256") == child_hash, "child_source_hash_fresh", "aggregate child source reference must match the current child report", report_type=report_type, expected=child_hash, observed=source.get("sha256"))
        if report_type in input_hashes:
            check(input_hashes[report_type] == child_hash, "child_input_hash_fresh", "aggregate input_hashes must match the current child report", report_type=report_type, expected=child_hash, observed=input_hashes[report_type])
        child, child_error = read_json(path)
        if child_error or not isinstance(child, dict):
            check(False, "child_report_json_invalid", "indexed child report must be valid JSON object", report_type=report_type, message=child_error or "not an object")
            continue
        child_deck_hash = child.get("deck_sha256")
        if child_deck_hash:
            check(child_deck_hash == index_hash, "child_deck_hash_consistent", "child report deck hash must match the index", report_type=report_type, expected=index_hash, observed=child_deck_hash)
        if entry.get("step_ok") is False:
            check(not evidence or evidence.get("valid") is not True, "indexed_step_failure_visible", "a failed pipeline step cannot be hidden by a passing child report", report_type=report_type)

    report_index_hash = sha256(index_path) if index_path.is_file() else None
    aggregate_index_path = resolve_path(project_report.get("report_index_path"), base=project_report_path.parent)
    aggregate_index_hash = project_report.get("report_index_sha256")
    if aggregate_index_path:
        check(aggregate_index_path == index_path, "aggregate_index_path_consistent", "aggregate must point to the supplied report index", expected=str(index_path), observed=str(aggregate_index_path))
        check(aggregate_index_path.is_file(), "aggregate_index_present", "aggregate report index path must exist", path=str(aggregate_index_path))
    else:
        check(False, "aggregate_index_path_missing", "aggregate must record report_index_path")
    check(valid_hash(aggregate_index_hash), "report_index_hash_format", "aggregate report_index_sha256 must be a lowercase SHA-256", observed=aggregate_index_hash)
    if report_index_hash:
        check(aggregate_index_hash == report_index_hash, "report_index_hash_fresh", "aggregate must describe the current report index", expected=report_index_hash, observed=aggregate_index_hash)

    pipeline_sources = pipeline.get("source_references")
    index_sources = index.get("source_references")
    aggregate_sources = project_report.get("source_references")
    if actual_deck and observed_deck_hash:
        check(source_matches(pipeline_sources, path=actual_deck, digest=observed_deck_hash, source_id="deck", base=pipeline_path.parent), "pipeline_deck_source", "pipeline source references must include the current deck")
        check(source_matches(index_sources, path=actual_deck, digest=observed_deck_hash, source_id="deck", base=index_path.parent), "index_deck_source", "report index source references must include the current deck")
        check(source_matches(aggregate_sources, path=actual_deck, digest=observed_deck_hash, source_id="deck", base=project_report_path.parent), "aggregate_deck_source", "aggregate source references must include the current deck")
    for report_type, evidence in evidence_by_type.items():
        if not isinstance(evidence, dict):
            continue
        source = evidence.get("source") if isinstance(evidence.get("source"), dict) else {}
        source_path = resolve_path(source.get("path"), base=project_report_path.parent)
        if source_path and source_path.is_file():
            check(source_matches(aggregate_sources, path=source_path, digest=source.get("sha256"), base=project_report_path.parent), "aggregate_child_source", "aggregate source references must retain each child source", report_type=report_type)

    steps = pipeline.get("steps") if isinstance(pipeline.get("steps"), list) else []
    unnamed_failed_steps = [step for step in steps if isinstance(step, dict) and step.get("ok") is not True and not isinstance(step.get("name"), str)]
    check(not unnamed_failed_steps, "failed_step_name_present", "every failed pipeline step must have a name")
    actual_failed = {step.get("name") for step in steps if isinstance(step, dict) and step.get("ok") is not True and isinstance(step.get("name"), str)}
    declared_failed = {name for name in (pipeline.get("failed_steps") or []) if isinstance(name, str)} if isinstance(pipeline.get("failed_steps"), list) else set()
    declared_technical_failed = {name for name in (pipeline.get("technical_failed_steps") or []) if isinstance(name, str)} if isinstance(pipeline.get("technical_failed_steps"), list) else set()
    expected_technical_failed = actual_failed - NON_TECHNICAL_STEPS
    check(declared_failed == actual_failed, "failed_steps_complete", "failed_steps must list every failed pipeline step", expected=sorted(actual_failed), observed=sorted(declared_failed))
    check(declared_technical_failed == expected_technical_failed, "technical_failed_steps_complete", "technical_failed_steps must not hide a failed technical step", expected=sorted(expected_technical_failed), observed=sorted(declared_technical_failed))
    check(pipeline.get("valid") is pipeline.get("technical_valid"), "technical_truth_alias", "pipeline valid must equal technical_valid")
    expected_pipeline_status = "passed" if pipeline.get("technical_valid") is True else "failed"
    check(pipeline.get("status") == expected_pipeline_status, "pipeline_status_consistent", "pipeline status must match technical_valid", expected=expected_pipeline_status, observed=pipeline.get("status"))
    if pipeline.get("release_eligible") is True:
        release_evidence = pipeline.get("release_evidence") if isinstance(pipeline.get("release_evidence"), dict) else {}
        check(pipeline.get("technical_valid") is True, "release_requires_technical_valid", "release eligibility requires a passing technical pipeline")
        check(release_evidence.get("report_bundle_valid") is True, "release_requires_bundle", "release eligibility requires a passing report bundle")
        check(release_evidence.get("human_signoff_valid") is True, "release_requires_signoff", "release eligibility requires validated human sign-off")
        check(release_evidence.get("release_check_passed") is True, "release_requires_delivery_check", "release eligibility requires a passing delivery check")
        finalization = pipeline.get("finalization") if isinstance(pipeline.get("finalization"), dict) else {}
        bundle_finalization = finalization.get("report_bundle") if isinstance(finalization.get("report_bundle"), dict) else {}
        check(bundle_finalization.get("status") == "passed", "release_requires_final_bundle", "release eligibility requires a sealed final report bundle")
    aggregate_valid = project_report.get("valid") is True and project_report.get("technical_valid") is True
    if aggregate_valid:
        check("project-report-aggregate" not in declared_technical_failed, "aggregate_step_truth", "a passing aggregate cannot have a failed aggregate step")
    if project_report.get("valid") is False:
        check("project-report-aggregate" in declared_technical_failed or pipeline.get("technical_valid") is not True, "aggregate_failure_visible", "a failed aggregate must be visible in technical pipeline status")
    check(project_report.get("valid") is project_report.get("technical_valid"), "aggregate_truth_alias", "aggregate valid must equal technical_valid")
    check(project_report.get("release_eligible") is not True, "aggregate_release_honesty", "project aggregate must not claim release eligibility before final release gates")
    check(project_report.get("may_claim_complete") is not True, "aggregate_completion_honesty", "project aggregate must not claim human closeout completion")

    if review_html_path:
        review_exists = review_html_path.is_file()
        check(review_exists, "review_html_present", "requested review HTML must exist", path=str(review_html_path))
        if review_exists:
            try:
                review = review_html_path.read_text(encoding="utf-8")
            except OSError as exc:
                review = ""
                check(False, "review_html_readable", "review HTML must be readable", message=str(exc))
            expected_labels = ["技术通过" if pipeline.get("technical_valid") is True else "技术阻断", "可交付" if pipeline.get("release_eligible") is True else "未放行"]
            if pipeline.get("human_review_required") is True:
                expected_labels.append("人工已复核" if str(pipeline.get("human_review_status", "")).lower() in {"approved", "passed", "complete", "completed", "signed-off", "signed_off"} else "人工待审")
            for label in expected_labels:
                check(label in review, "review_status_consistent", "review HTML must display the pipeline status", label=label)

    review_html_hash = sha256(review_html_path) if review_html_path and review_html_path.is_file() else None

    status = "passed" if not issues else "failed"
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "report_type": REPORT_TYPE,
        "project_id": index.get("project_id") or pipeline.get("project"),
        "revision": index.get("revision"),
        "stage": index.get("stage", "validated"),
        "validation_scope": scope,
        "full_deck_validation_required": expected_full_required,
        "valid": not issues,
        "status": status,
        "technical_valid": not issues,
        "technical_status": "passed" if not issues else "failed",
        "human_review_required": True,
        "human_review_status": "pending",
        "release_eligible": False,
        "release_status": "blocked-pending-bundle-and-human-gates",
        "deck_path": str(actual_deck) if actual_deck else None,
        "deck_sha256": observed_deck_hash or pipeline_hash or index_hash,
        "report_index_path": str(index_path),
        "report_index_sha256": report_index_hash,
        "pipeline_result_path": str(pipeline_path),
        "pipeline_result_sha256": pipeline_result_hash,
        "project_report_path": str(project_report_path),
        "review_html_path": str(review_html_path) if review_html_path else None,
        "review_html_sha256": review_html_hash,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool": "ai-ppt-plus/validate_report_bundle.py",
        "checks": checks,
        "issues": issues,
        "source_references": [
            {"source_id": "deck", "path": str(actual_deck), "sha256": observed_deck_hash or pipeline_hash} if actual_deck else {"source_id": "deck", "path": None, "sha256": pipeline_hash},
            {"source_id": "report-index", "path": str(index_path), "sha256": report_index_hash},
            {"source_id": "project-report", "path": str(project_report_path), "sha256": sha256(project_report_path) if project_report_path.is_file() else None},
            {"source_id": "pipeline-result", "path": str(pipeline_path), "sha256": pipeline_result_hash},
            *([{"source_id": "review-html", "path": str(review_html_path), "sha256": review_html_hash}] if review_html_path else []),
        ],
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pipeline_result")
    parser.add_argument("--report-index", required=True)
    parser.add_argument("--project-report", required=True)
    parser.add_argument("--deck")
    parser.add_argument("--review-html")
    parser.add_argument("--require-full", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()

    pipeline_path = Path(args.pipeline_result).resolve()
    index_path = Path(args.report_index).resolve()
    project_report_path = Path(args.project_report).resolve()
    pipeline, pipeline_error = read_json(pipeline_path)
    index, index_error = read_json(index_path)
    project_report, project_error = read_json(project_report_path)
    errors = []
    for label, error in (("pipeline_result", pipeline_error), ("report_index", index_error), ("project_report", project_error)):
        if error:
            errors.append({"severity": "blocker", "code": f"{label}_invalid", "message": error})
    report = validate_bundle(
        pipeline,
        pipeline_path,
        index,
        index_path,
        project_report,
        project_report_path,
        deck_path=Path(args.deck).resolve() if args.deck else None,
        require_full=args.require_full,
        review_html_path=Path(args.review_html).resolve() if args.review_html else None,
    )
    if errors:
        report["issues"] = errors + report.get("issues", [])
        report["valid"] = False
        report["technical_valid"] = False
        report["status"] = "failed"
        report["technical_status"] = "failed"
    if args.report:
        output = Path(args.report).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())