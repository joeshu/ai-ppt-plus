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

def audit(plan: dict, coverage: dict, *, plan_sha256: str) -> dict:
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

        evidence = entry.get("text_fit_evidence")
        if not isinstance(evidence, dict) or evidence.get("measured") is not True:
            issues.append(problem("text_coverage_measurement_missing", "text_fit_evidence.measured must be true", target_id=target_id, owner_object_id=owner_id if isinstance(owner_id, str) else None))
        elif not isinstance(evidence.get("fit_decision"), str) or not evidence.get("fit_decision", "").strip():
            issues.append(problem("text_coverage_fit_decision_missing", "text_fit_evidence.fit_decision is required", target_id=target_id, owner_object_id=owner_id if isinstance(owner_id, str) else None))

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
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        plan = load_json(args.authoring_plan)
        coverage = load_json(args.coverage)
        result = audit(plan, coverage, plan_sha256=sha256(args.authoring_plan))
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
