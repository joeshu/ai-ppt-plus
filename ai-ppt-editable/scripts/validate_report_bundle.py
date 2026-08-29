#!/usr/bin/env python3
"""Validate freshness and cross-artifact consistency of a pipeline report bundle.

The project aggregate validates its indexed child reports, but a downstream
consumer also needs to know that the pipeline result, report index, aggregate,
and deck all describe the same run.  This read-only gate checks that boundary.

Usage: validate_report_bundle.py PIPELINE_RESULT
       --report-index report-index.json --project-report project-report.json
       [--deck deck.pptx] [--review-html review.html] [--require-full]
       [--report report-bundle-validation.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json

try:
    from schema_contract import validate as validate_schema
except ImportError:  # pragma: no cover - allows embedding the module elsewhere
    validate_schema = None


SCHEMA = "ai-ppt-plus/report-envelope/v1"
REPORT_TYPE = "report-bundle-validation"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
NON_TECHNICAL_STEPS = {"signoff-validation", "release-check"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> tuple[Any, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # the report must explain malformed inputs
        return None, f"{type(exc).__name__}: {exc}"


def resolve_path(value: Any, *, base: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def valid_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def source_matches(sources: Any, *, path: Path | None = None, digest: str | None = None, source_id: str | None = None, base: Path | None = None) -> bool:
    if not isinstance(sources, list):
        return False
    resolved_path = path.resolve() if path else None
    source_base = base.resolve() if base else Path.cwd().resolve()
    for source in sources:
        if not isinstance(source, dict):
            continue
        if source_id and source.get("source_id") != source_id:
            continue
        source_path = resolve_path(source.get("path"), base=source_base)
        if resolved_path and source_path and source_path == resolved_path:
            return not digest or source.get("sha256") == digest
        if resolved_path:
            continue
        if digest and source.get("sha256") == digest:
            return True
        if not digest and not resolved_path:
            return True
    return False


def schema_issues(value: Any, filename: str, *, schema_dir: Path) -> list[dict[str, Any]]:
    if validate_schema is None:
        return []
    path = schema_dir / filename
    if not path.is_file():
        return [{"severity": "blocker", "code": "schema_missing", "schema": str(path)}]
    schema, error = read_json(path)
    if error or not isinstance(schema, dict):
        return [{"severity": "blocker", "code": "schema_invalid", "schema": str(path), "message": error or "schema must be an object"}]
    return [
        {"severity": "blocker", "code": "schema_validation_failed", "schema": filename, **item}
        for item in validate_schema(value, schema)
    ]


def _report_entry_paths(index: dict[str, Any], index_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return normalized index entries and structural issues."""
    issues: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    raw_reports = index.get("reports")
    if not isinstance(raw_reports, list) or not raw_reports:
        return entries, [{"severity": "blocker", "code": "report_index_empty"}]
    seen_types: set[str] = set()
    for position, raw in enumerate(raw_reports):
        if not isinstance(raw, dict):
            issues.append({"severity": "blocker", "code": "report_entry_not_object", "index": position})
            continue
        report_type = raw.get("report_type")
        if not isinstance(report_type, str) or not report_type.strip():
            issues.append({"severity": "blocker", "code": "report_type_missing", "index": position})
            continue
        if report_type in seen_types:
            issues.append({"severity": "blocker", "code": "duplicate_report_type", "report_type": report_type})
        seen_types.add(report_type)
        report_path = resolve_path(raw.get("path"), base=index_path.parent)
        if report_path is None:
            issues.append({"severity": "blocker" if raw.get("required") is True else "major", "code": "report_path_missing", "report_type": report_type})
            continue
        entries.append({**raw, "report_type": report_type, "resolved_path": report_path})
    return entries, issues


def validate_bundle(
    pipeline: Any,
    pipeline_path: Path,
    index: Any,
    index_path: Path,
    project_report: Any,
    project_report_path: Path,
    *,
    deck_path: Path | None = None,
    require_full: bool = False,
    review_html_path: Path | None = None,
) -> dict[str, Any]:
    """Return a machine-readable report; never mutates input artifacts."""
    issues: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    def check(ok: bool, code: str, message: str, **details: Any) -> None:
        item = {"code": code, "status": "passed" if ok else "failed", "message": message}
        item.update(details)
        checks.append(item)
        if not ok:
            issues.append({"severity": "blocker", **item})

    pipeline = pipeline if isinstance(pipeline, dict) else {}
    index = index if isinstance(index, dict) else {}
    project_report = project_report if isinstance(project_report, dict) else {}

    check(pipeline_path.is_file(), "pipeline_result_present", "pipeline-result.json must exist", path=str(pipeline_path))
    check(index_path.is_file(), "report_index_present", "report-index.json must exist", path=str(index_path))
    check(project_report_path.is_file(), "project_report_present", "project-report.json must exist", path=str(project_report_path))
    check(bool(pipeline), "pipeline_result_object", "pipeline-result.json must contain an object")
    check(bool(index), "report_index_object", "report-index.json must contain an object")
    check(bool(project_report), "project_report_object", "project-report.json must contain an object")

    pipeline_result_hash = sha256(pipeline_path) if pipeline_path.is_file() else None
    check(pipeline_result_hash is not None, "pipeline_result_hash_present", "the final pipeline result must be hashable")

    root = Path(__file__).resolve().parents[1]
    if pipeline:
        issues.extend(schema_issues(pipeline, "pipeline-run.schema.json", schema_dir=root / "assets" / "schemas"))
    if index:
        issues.extend(schema_issues(index, "report-index.schema.json", schema_dir=root / "assets" / "schemas"))
    if project_report:
        issues.extend(schema_issues(project_report, "report-envelope.schema.json", schema_dir=root / "assets" / "schemas"))

    actual_deck = deck_path or resolve_path(pipeline.get("deck"), base=pipeline_path.parent) or resolve_path(index.get("deck_path"), base=index_path.parent)
    observed_deck_hash = sha256(actual_deck) if actual_deck and actual_deck.is_file() else None
    pipeline_hash = pipeline.get("deck_sha256")
    index_hash = index.get("deck_sha256")
    aggregate_hash = project_report.get("deck_sha256")
    hash_values = {"pipeline": pipeline_hash, "report_index": index_hash, "project_report": aggregate_hash}
    for label, value in hash_values.items():
        check(valid_hash(value), "deck_hash_format", f"{label} deck_sha256 must be a lowercase SHA-256", artifact=label, observed=value)
    if actual_deck:
        check(actual_deck.is_file(), "deck_present", "the referenced PPTX must exist", path=str(actual_deck))
    else:
        check(False, "deck_path_missing", "a deck path is required in pipeline-result.json, report-index.json, or --deck")
    if observed_deck_hash:
        for label, value in hash_values.items():
            check(value == observed_deck_hash, "deck_hash_fresh", f"{label} must describe the current PPTX", artifact=label, expected=observed_deck_hash, observed=value)
    check(pipeline_hash == index_hash == aggregate_hash, "deck_hash_consistent", "pipeline, index, and aggregate must share one deck hash", values=hash_values)

    scope_values = {"pipeline": pipeline.get("validation_scope"), "report_index": index.get("validation_scope"), "project_report": project_report.get("validation_scope")}
    scope_values_list = list(scope_values.values())
    scope_values_valid = all(isinstance(value, str) and value in {"full", "incremental"} for value in scope_values_list)
    check(scope_values_valid, "validation_scope_format", "all reports must declare full or incremental validation", values=scope_values)
    check(len(scope_values_list) == 3 and scope_values_list[0] == scope_values_list[1] == scope_values_list[2], "validation_scope_consistent", "pipeline, index, and aggregate validation scopes must agree", values=scope_values)
    scope = pipeline.get("validation_scope")
    expected_full_required = scope == "incremental"
    check(pipeline.get("full_deck_validation_required") is expected_full_required, "pipeline_scope_flag", "pipeline full_deck_validation_required must match its validation scope", observed=pipeline.get("full_deck_validation_required"), expected=expected_full_required)
    check(project_report.get("full_deck_validation_required") is expected_full_required, "aggregate_scope_flag", "aggregate full_deck_validation_required must match its validation scope", observed=project_report.get("full_deck_validation_required"), expected=expected_full_required)
    if require_full:
        check(scope == "full", "full_validation_required", "this consumer requires a full-deck report bundle", observed=scope)
    execution = pipeline.get("execution") if isinstance(pipeline.get("execution"), dict) else {}
    affected_pages = execution.get("affected_pages")
    if scope == "incremental":
        check(isinstance(affected_pages, list) and bool(affected_pages), "incremental_pages_declared", "incremental bundles must declare affected pages", observed=affected_pages)
    elif scope == "full":
        check(affected_pages in (None, "all", []), "full_scope_pages", "full bundles must not masquerade as a page subset", observed=affected_pages)

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
        atomic_write_json(output.resolve(), report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
