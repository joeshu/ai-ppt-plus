#!/usr/bin/env python3
"""Fail-closed gate for promoting reconstruction candidates to versioned golden baselines."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GoldenPromotionPolicy:
    min_pixel_fidelity_score: float = 0.94
    required_semantic_accuracy: float = 1.0
    min_consecutive_stable_iterations: int = 2
    require_native_editability: bool = True
    require_zero_drift: bool = True
    require_human_approval: bool = True
    require_no_rollback: bool = True
    require_zero_blockers: bool = True
    require_semantic_audit: bool = True
    require_complete_semantic_object_coverage: bool = True


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _semantic_evidence(record: dict[str, Any], policy: GoldenPromotionPolicy) -> tuple[dict[str, Any], list[str]]:
    """Validate semantic evidence independently from the top-level summary score.

    A top-level semantic_accuracy value is only a summary. Golden promotion also
    requires the underlying semantic audit to exist, be valid, contain no errors,
    and prove complete object coverage. This prevents fabricated or stale summary
    values from bypassing semantic reconstruction validation.
    """
    reasons: list[str] = []
    semantic_value = _number(record.get("semantic_accuracy"))
    audit = record.get("semantic_audit")

    evidence: dict[str, Any] = {
        "semantic_accuracy": semantic_value,
        "semantic_audit_present": isinstance(audit, dict),
        "semantic_audit_valid": None,
        "semantic_audit_accuracy": None,
        "semantic_error_count": None,
        "semantic_warning_count": None,
        "semantic_expected_object_count": None,
        "semantic_audited_object_count": None,
        "semantic_object_coverage_complete": False,
    }

    if semantic_value is None:
        reasons.append("missing_semantic_accuracy")
    elif semantic_value != policy.required_semantic_accuracy:
        reasons.append("semantic_accuracy_not_perfect")

    if not policy.require_semantic_audit:
        return evidence, reasons
    if not isinstance(audit, dict):
        reasons.append("semantic_audit_missing")
        return evidence, reasons

    audit_valid = audit.get("valid") is True
    audit_accuracy = _number(audit.get("accuracy"))
    error_count = _nonnegative_int(audit.get("error_count"))
    warning_count = _nonnegative_int(audit.get("warning_count"))
    expected_count = _nonnegative_int(audit.get("expected_object_count"))
    audited_count = _nonnegative_int(audit.get("audited_object_count"))

    evidence.update({
        "semantic_audit_valid": audit_valid,
        "semantic_audit_accuracy": audit_accuracy,
        "semantic_error_count": error_count,
        "semantic_warning_count": warning_count,
        "semantic_expected_object_count": expected_count,
        "semantic_audited_object_count": audited_count,
        "semantic_object_coverage_complete": (
            expected_count is not None and audited_count is not None and audited_count == expected_count
        ),
    })

    if not audit_valid:
        reasons.append("semantic_audit_invalid")
    if audit_accuracy is None:
        reasons.append("semantic_audit_accuracy_missing")
    elif audit_accuracy != policy.required_semantic_accuracy:
        reasons.append("semantic_audit_accuracy_not_perfect")
    if semantic_value is not None and audit_accuracy is not None and semantic_value != audit_accuracy:
        reasons.append("semantic_accuracy_mismatch")
    if error_count is None:
        reasons.append("semantic_audit_error_count_missing")
    elif error_count != 0:
        reasons.append("semantic_audit_errors_present")

    if policy.require_complete_semantic_object_coverage:
        if expected_count is None or audited_count is None:
            reasons.append("semantic_audit_object_counts_missing")
        elif audited_count != expected_count:
            reasons.append("semantic_audit_incomplete")

    return evidence, reasons


def _eligible(record: dict[str, Any], policy: GoldenPromotionPolicy) -> tuple[bool, list[str], dict[str, Any]]:
    reasons: list[str] = []
    score = record.get("pixel_fidelity_score")
    if record.get("accepted") is not True:
        reasons.append("not_accepted")
    if policy.require_no_rollback and record.get("rollback") is True:
        reasons.append("rollback_present")
    if policy.require_zero_drift and int(record.get("unauthorized_object_drift_count") or 0) != 0:
        reasons.append("object_drift_present")
    if policy.require_native_editability and record.get("native_editability_valid") is not True:
        reasons.append("native_editability_invalid")
    if policy.require_zero_blockers and int(record.get("blocking_count") or 0) != 0:
        reasons.append("blocking_findings_present")

    score_value = _number(score)
    if score_value is None:
        reasons.append("missing_pixel_fidelity_score")
    elif score_value < policy.min_pixel_fidelity_score:
        reasons.append("pixel_fidelity_below_threshold")

    semantic_evidence, semantic_reasons = _semantic_evidence(record, policy)
    reasons.extend(semantic_reasons)

    if policy.require_human_approval and record.get("human_approved") is not True:
        reasons.append("human_approval_missing")
    return not reasons, reasons, semantic_evidence


def evaluate_case(records: list[dict[str, Any]], *, policy: GoldenPromotionPolicy | None = None) -> dict[str, Any]:
    policy = policy or GoldenPromotionPolicy()
    ordered = sorted(records, key=lambda r: int(r.get("iteration") or 0))
    streak: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    for record in ordered:
        ok, reasons, semantic_evidence = _eligible(record, policy)
        evaluations.append({
            "iteration": int(record.get("iteration") or 0),
            "eligible": ok,
            "reasons": reasons,
            "semantic_evidence": semantic_evidence,
        })
        if ok:
            streak.append(record)
        else:
            streak = []
    promotable = len(streak) >= policy.min_consecutive_stable_iterations
    latest = ordered[-1] if ordered else {}
    latest_evaluation = evaluations[-1] if evaluations else {}
    return {
        "schema": "ai-ppt-plus/golden-promotion-evaluation/v2",
        "case_id": latest.get("case_id"),
        "promotable": promotable,
        "stable_streak": len(streak),
        "required_streak": policy.min_consecutive_stable_iterations,
        "candidate_iteration": int(latest.get("iteration") or 0) if promotable else None,
        "candidate_artifacts": dict(latest.get("artifacts") or {}) if promotable else {},
        "candidate_semantic_evidence": dict(latest_evaluation.get("semantic_evidence") or {}) if promotable else {},
        "evaluations": evaluations,
        "policy": {
            "min_pixel_fidelity_score": policy.min_pixel_fidelity_score,
            "required_semantic_accuracy": policy.required_semantic_accuracy,
            "min_consecutive_stable_iterations": policy.min_consecutive_stable_iterations,
            "require_native_editability": policy.require_native_editability,
            "require_zero_drift": policy.require_zero_drift,
            "require_human_approval": policy.require_human_approval,
            "require_no_rollback": policy.require_no_rollback,
            "require_zero_blockers": policy.require_zero_blockers,
            "require_semantic_audit": policy.require_semantic_audit,
            "require_complete_semantic_object_coverage": policy.require_complete_semantic_object_coverage,
        },
    }


def build_promotion_manifest(*, evaluation: dict[str, Any], previous_golden: dict[str, Any] | None,
                             version: str) -> dict[str, Any]:
    if evaluation.get("promotable") is not True:
        raise ValueError("candidate has not passed golden promotion gate")
    if not version or not str(version).strip():
        raise ValueError("version is required")
    previous_golden = dict(previous_golden or {})
    previous_version = previous_golden.get("version")
    if previous_version == version:
        raise ValueError("golden version must be immutable; choose a new version")
    return {
        "schema": "ai-ppt-plus/golden-baseline-manifest/v2",
        "version": str(version),
        "case_id": evaluation.get("case_id"),
        "source_iteration": evaluation.get("candidate_iteration"),
        "artifacts": dict(evaluation.get("candidate_artifacts") or {}),
        "semantic_evidence": dict(evaluation.get("candidate_semantic_evidence") or {}),
        "previous_golden": previous_golden or None,
        "rollback_to_version": previous_version,
        "promotion_evidence": evaluation,
        "immutable": True,
    }
