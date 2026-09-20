#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

PLAN_SCHEMA = "ai-ppt-plus/authoring-plan/v1"
COVERAGE_SCHEMA = "ai-ppt-plus/text-coverage/v1"
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
MEASUREMENT_SCOPES = {"whole_phrase", "sub_box"}
ALLOWED_PRODUCERS = {
    "text_box", "rich_text_runs", "table_cell", "badge_label",
    "chart_label", "number_unit", "other",
}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

def problem(code: str, detail: str, *, target_id: str | None = None, owner_object_id: str | None = None) -> dict:
    item = {"severity": "blocker", "code": code, "detail": detail}
    if target_id:
        item["target_id"] = target_id
    if owner_object_id:
        item["owner_object_id"] = owner_object_id
    return item

def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _validate_trace(entry: dict, evidence: dict, *, expected: str, producer: str, target_id: str, owner_id: str | None) -> list[dict]:
    issues: list[dict] = []
    context = {"target_id": target_id, "owner_object_id": owner_id} if owner_id else {"target_id": target_id}
    text_spec_id = entry.get("text_spec_id")
    if not isinstance(text_spec_id, str) or not text_spec_id.strip():
        issues.append(problem("text_coverage_text_spec_id_missing", "text_spec_id is required", **context))

    content_sha = evidence.get("content_sha256")
    if not isinstance(content_sha, str) or not SHA256_RE.match(content_sha):
        issues.append(problem("text_coverage_content_sha_missing", "text_fit_evidence.content_sha256 must be a SHA-256", **context))
    elif content_sha.lower() != sha256_text(expected).lower():
        issues.append(problem("text_coverage_content_sha_mismatch", "measurement content hash does not match expected_text", **context))
    if entry.get("content_sha256") is not None and entry.get("content_sha256") != content_sha:
        issues.append(problem("text_coverage_entry_evidence_mismatch", "entry.content_sha256 must equal text_fit_evidence.content_sha256", **context))

    run_count = evidence.get("run_count")
    if not isinstance(run_count, int) or isinstance(run_count, bool) or run_count < 0:
        issues.append(problem("text_coverage_run_count_invalid", "run_count must be a non-negative integer", **context))
        run_count = 0
    run_ids = evidence.get("run_ids")
    if not isinstance(run_ids, list) or any(not isinstance(run_id, str) or not run_id.strip() for run_id in run_ids):
        issues.append(problem("text_coverage_run_ids_invalid", "run_ids must be a list of non-empty strings", **context))
        run_ids = []
    if len(run_ids) != len(set(run_ids)):
        issues.append(problem("text_coverage_run_ids_duplicate", "run_ids must be unique", **context))
    if len(run_ids) != run_count:
        issues.append(problem("text_coverage_run_count_mismatch", "run_count must equal len(run_ids)", **context))

    run_trace = evidence.get("run_trace")
    if not isinstance(run_trace, list):
        issues.append(problem("text_coverage_run_trace_missing", "run_trace must be a list", **context))
        run_trace = []
    if run_count > 0 or producer == "rich_text_runs":
        if run_count <= 0:
            issues.append(problem("text_coverage_rich_runs_missing", "rich_text_runs must expose at least one measured run", **context))
        if len(run_trace) != run_count:
            issues.append(problem("text_coverage_run_trace_count_mismatch", "run_trace length must equal run_count", **context))
        trace_ids = []
        trace_text = []
        for index, run in enumerate(run_trace):
            if not isinstance(run, dict):
                issues.append(problem("text_coverage_run_trace_invalid", f"run_trace[{index}] must be an object", **context))
                continue
            run_id = run.get("run_id")
            if not isinstance(run_id, str) or not run_id.strip():
                issues.append(problem("text_coverage_run_trace_id_missing", f"run_trace[{index}].run_id is required", **context))
            trace_ids.append(run_id)
            run_text = run.get("text")
            if not isinstance(run_text, str):
                issues.append(problem("text_coverage_run_trace_text_invalid", f"run_trace[{index}].text must be a string", **context))
                run_text = ""
            trace_text.append(run_text)
            if not isinstance(run.get("style"), dict):
                issues.append(problem("text_coverage_run_trace_style_missing", f"run_trace[{index}].style must be an object", **context))
        if trace_ids != run_ids:
            issues.append(problem("text_coverage_run_trace_binding_mismatch", "run_trace IDs must equal run_ids in order", **context))
        if "".join(trace_text) != expected:
            issues.append(problem("text_coverage_run_trace_content_mismatch", "concatenated run_trace text must equal expected_text", **context))
        run_style_hash = evidence.get("run_style_sha256")
        if not isinstance(run_style_hash, str) or not SHA256_RE.match(run_style_hash):
            issues.append(problem("text_coverage_run_style_sha_missing", "run_style_sha256 is required for rich runs", **context))
        else:
            payload = [{"run_id": run.get("run_id"), "style": run.get("style", {})} for run in run_trace if isinstance(run, dict)]
            if run_style_hash.lower() != stable_digest(payload).lower():
                issues.append(problem("text_coverage_run_style_sha_mismatch", "run style trace hash does not match run_trace", **context))
        if evidence.get("content_matches_runs") is not True:
            issues.append(problem("text_coverage_runs_content_unverified", "content_matches_runs must be true for rich runs", **context))
    elif evidence.get("content_matches_runs") not in (None, True):
        issues.append(problem("text_coverage_runs_content_invalid", "content_matches_runs must be null or true without runs", **context))

    scope = evidence.get("measurement_scope")
    if not isinstance(scope, dict) or scope.get("kind") not in MEASUREMENT_SCOPES or not isinstance(scope.get("scope_id"), str) or not scope.get("scope_id"):
        issues.append(problem("text_coverage_measurement_scope_invalid", "measurement_scope must declare whole_phrase/sub_box and scope_id", **context))
    if entry.get("measurement_scope") is not None and entry.get("measurement_scope") != scope:
        issues.append(problem("text_coverage_entry_scope_mismatch", "entry.measurement_scope must equal text_fit_evidence.measurement_scope", **context))

    number_unit = evidence.get("number_unit") or entry.get("number_unit")
    if producer == "number_unit" or number_unit is not None:
        if not isinstance(number_unit, dict):
            issues.append(problem("text_coverage_number_unit_missing", "number_unit producer requires a number_unit trace", **context))
        else:
            for field in ("group_id", "number_text", "unit_text", "combined_text"):
                if not isinstance(number_unit.get(field), str) or not number_unit.get(field):
                    issues.append(problem("text_coverage_number_unit_field_missing", f"number_unit.{field} is required", **context))
            if number_unit.get("combined_text") != expected:
                issues.append(problem("text_coverage_number_unit_content_mismatch", "number_unit combined_text must equal expected_text", **context))
            for field in ("number_run_id", "unit_run_id"):
                if number_unit.get(field) is not None and number_unit[field] not in run_ids:
                    issues.append(problem("text_coverage_number_unit_run_unknown", f"number_unit.{field} must reference run_ids", **context))
    return issues

def audit(plan: dict, coverage: dict, *, plan_sha256: str, text_fit_report: dict | None = None) -> dict:
    issues: list[dict] = []
    if plan.get("schema") != PLAN_SCHEMA:
        issues.append(problem("text_coverage_plan_schema_invalid", f"expected {PLAN_SCHEMA}"))
    if coverage.get("schema") != COVERAGE_SCHEMA:
        issues.append(problem("text_coverage_schema_invalid", f"expected {COVERAGE_SCHEMA}"))

    objects = [x for x in (plan.get("objects") or []) if isinstance(x, dict)]
    by_id = {x.get("object_id"): x for x in objects if isinstance(x.get("object_id"), str) and x.get("object_id")}
    native_text_ids = {
        object_id for object_id, obj in by_id.items()
        if obj.get("implementation_type") == "native_text"
    }

    source = coverage.get("source")
    declared_sha = source.get("authoring_plan_sha256") if isinstance(source, dict) else None
    if not isinstance(declared_sha, str) or not SHA256_RE.match(declared_sha):
        issues.append(problem("text_coverage_plan_sha_missing", "source.authoring_plan_sha256 must be a SHA-256"))
    elif declared_sha.lower() != plan_sha256.lower():
        issues.append(problem("text_coverage_plan_sha_mismatch", "coverage is not bound to the supplied AuthoringPlan"))

    measured_ids: set[str] = set()
    fit_slots: dict[str, dict] = {}
    if text_fit_report is not None:
        if not str(text_fit_report.get("schema", "")).startswith("ai-ppt-plus/text-fit-deck/"):
            issues.append(problem("text_coverage_text_fit_schema_invalid", "text-fit report schema is invalid"))
        if text_fit_report.get("all_slots_measured") is not True:
            issues.append(problem("text_coverage_text_fit_incomplete", "text-fit report must declare all_slots_measured=true"))
        measured_ids = {str(x) for x in (text_fit_report.get("measured_object_ids") or []) if str(x)}
        for slot in text_fit_report.get("slots") or []:
            if not isinstance(slot, dict) or not isinstance(slot.get("object_id"), str):
                continue
            slot_id = slot["object_id"]
            if slot_id in fit_slots:
                issues.append(problem("text_coverage_text_fit_duplicate_slot", "text-fit report contains duplicate object_id", target_id=slot_id))
            fit_slots[slot_id] = slot
    else:
        issues.append(problem("text_coverage_text_fit_report_missing", "--text-fit-report is required to bind coverage to measured text"))

    entries = coverage.get("entries")
    if not isinstance(entries, list):
        issues.append(problem("text_coverage_entries_missing", "entries must be a list"))
        entries = []

    seen_targets: set[str] = set()
    seen_bindings: set[tuple[str, str]] = set()
    covered_native: set[str] = set()

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            issues.append(problem("text_coverage_entry_invalid", f"entry {index} must be an object"))
            continue
        target_id = entry.get("target_id")
        owner_id = entry.get("owner_object_id")
        if not isinstance(target_id, str) or not target_id.strip():
            issues.append(problem("text_coverage_target_missing", f"entry {index} target_id is required"))
            continue
        if target_id in seen_targets:
            issues.append(problem("text_coverage_target_duplicate", "target_id must be unique", target_id=target_id))
        else:
            seen_targets.add(target_id)

        if not isinstance(owner_id, str) or owner_id not in by_id:
            issues.append(problem("text_coverage_owner_unknown", "owner_object_id must exist in AuthoringPlan", target_id=target_id, owner_object_id=str(owner_id) if owner_id else None))
        elif owner_id in native_text_ids:
            covered_native.add(owner_id)

        producer = entry.get("producer_kind")
        if producer not in ALLOWED_PRODUCERS:
            issues.append(problem("text_coverage_producer_invalid", f"producer_kind must be one of {sorted(ALLOWED_PRODUCERS)}", target_id=target_id, owner_object_id=owner_id if isinstance(owner_id, str) else None))

        required = entry.get("formal_text_required", True) is not False
        expected = entry.get("expected_text")
        if not isinstance(expected, str) or (required and not expected.strip()):
            issues.append(problem("text_coverage_expected_text_missing", "required formal text must be non-empty", target_id=target_id, owner_object_id=owner_id if isinstance(owner_id, str) else None))

        path = entry.get("authoring_path")
        if not isinstance(path, str) or not path.strip():
            issues.append(problem("text_coverage_authoring_path_missing", "authoring_path is required", target_id=target_id, owner_object_id=owner_id if isinstance(owner_id, str) else None))

        evidence_id = entry.get("text_fit_evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            issues.append(problem("text_coverage_evidence_id_missing", "text_fit_evidence_id is required", target_id=target_id, owner_object_id=owner_id if isinstance(owner_id, str) else None))
        elif measured_ids is not None and evidence_id not in measured_ids:
            issues.append(problem("text_coverage_evidence_id_unmeasured", "text_fit_evidence_id is absent from measured_object_ids", target_id=target_id, owner_object_id=owner_id if isinstance(owner_id, str) else None))

        evidence = entry.get("text_fit_evidence")
        if not isinstance(evidence, dict) or evidence.get("measured") is not True:
            issues.append(problem("text_coverage_measurement_missing", "text_fit_evidence.measured must be true", target_id=target_id, owner_object_id=owner_id if isinstance(owner_id, str) else None))
        elif not isinstance(evidence.get("fit_decision"), str) or not evidence.get("fit_decision", "").strip():
            issues.append(problem("text_coverage_fit_decision_missing", "text_fit_evidence.fit_decision is required", target_id=target_id, owner_object_id=owner_id if isinstance(owner_id, str) else None))
        elif isinstance(expected, str):
            issues.extend(_validate_trace(
                entry,
                evidence,
                expected=expected,
                producer=producer if isinstance(producer, str) else "other",
                target_id=target_id,
                owner_id=owner_id if isinstance(owner_id, str) else None,
            ))

        if evidence_id in fit_slots:
            slot = fit_slots[evidence_id]
            slot_text = slot.get("text")
            if not isinstance(slot_text, str) or slot_text != expected:
                issues.append(problem("text_coverage_text_fit_content_mismatch", "coverage expected_text differs from measured slot text", target_id=target_id, owner_object_id=owner_id if isinstance(owner_id, str) else None))
            if slot.get("trace_defects"):
                issues.append(problem("text_coverage_text_fit_trace_defect", "measured slot contains text trace defects", target_id=target_id, owner_object_id=owner_id if isinstance(owner_id, str) else None))
            for key in ("text_spec_id", "content_sha256", "run_count", "run_ids", "measurement_scope"):
                slot_value = slot.get(key)
                evidence_value = evidence.get(key)
                if slot_value is not None and evidence_value != slot_value:
                    issues.append(problem("text_coverage_text_fit_trace_mismatch", f"{key} differs from measured slot", target_id=target_id, owner_object_id=owner_id if isinstance(owner_id, str) else None))

        binding = entry.get("output_binding")
        if not isinstance(binding, dict):
            issues.append(problem("text_coverage_output_binding_missing", "output_binding is required", target_id=target_id, owner_object_id=owner_id if isinstance(owner_id, str) else None))
        else:
            kind = binding.get("kind")
            binding_id = binding.get("binding_id")
            if not isinstance(kind, str) or not kind.strip() or not isinstance(binding_id, str) or not binding_id.strip():
                issues.append(problem("text_coverage_output_binding_invalid", "output_binding.kind and binding_id are required", target_id=target_id, owner_object_id=owner_id if isinstance(owner_id, str) else None))
            else:
                key = (kind, binding_id)
                if key in seen_bindings:
                    issues.append(problem("text_coverage_output_binding_duplicate", "output binding must identify one formal-text target", target_id=target_id, owner_object_id=owner_id if isinstance(owner_id, str) else None))
                seen_bindings.add(key)

    uncovered = sorted(native_text_ids - covered_native)
    for object_id in uncovered:
        issues.append(problem("text_coverage_native_text_uncovered", "native_text AuthoringPlan object has no coverage entry", owner_object_id=object_id))

    return {
        "schema": "ai-ppt-plus/text-coverage-audit/v1",
        "valid": not issues,
        "status": "passed" if not issues else "failed",
        "authoring_plan_sha256": plan_sha256,
        "native_text_owner_count": len(native_text_ids),
        "coverage_entry_count": len(entries),
        "uncovered_native_text": uncovered,
        "issues": issues,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Audit formal-text producer coverage against AuthoringPlan.")
    parser.add_argument("authoring_plan", type=Path)
    parser.add_argument("coverage", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--text-fit-report", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        plan = load_json(args.authoring_plan)
        coverage = load_json(args.coverage)
        text_fit_report = load_json(args.text_fit_report) if args.text_fit_report else None
        result = audit(plan, coverage, plan_sha256=sha256(args.authoring_plan), text_fit_report=text_fit_report)
    except Exception as exc:
        result = {
            "schema": "ai-ppt-plus/text-coverage-audit/v1",
            "valid": False,
            "status": "failed",
            "authoring_plan_sha256": None,
            "native_text_owner_count": 0,
            "coverage_entry_count": 0,
            "uncovered_native_text": [],
            "issues": [problem("text_coverage_unreadable", str(exc))],
        }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json or not args.report:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
