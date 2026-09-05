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


def _eligible(record: dict[str, Any], policy: GoldenPromotionPolicy) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    score = record.get("pixel_fidelity_score")
    semantic = record.get("semantic_accuracy")
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
    try:
        score_value = float(score)
    except (TypeError, ValueError):
        score_value = None
    if score_value is None:
        reasons.append("missing_pixel_fidelity_score")
    elif score_value < policy.min_pixel_fidelity_score:
        reasons.append("pixel_fidelity_below_threshold")
    try:
        semantic_value = float(semantic)
    except (TypeError, ValueError):
        semantic_value = None
    if semantic_value is None:
        reasons.append("missing_semantic_accuracy")
    elif semantic_value != policy.required_semantic_accuracy:
        reasons.append("semantic_accuracy_not_perfect")
    if policy.require_human_approval and record.get("human_approved") is not True:
        reasons.append("human_approval_missing")
    return not reasons, reasons


def evaluate_case(records: list[dict[str, Any]], *, policy: GoldenPromotionPolicy | None = None) -> dict[str, Any]:
    policy = policy or GoldenPromotionPolicy()
    ordered = sorted(records, key=lambda r: int(r.get("iteration") or 0))
    streak: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    for record in ordered:
        ok, reasons = _eligible(record, policy)
        evaluations.append({
            "iteration": int(record.get("iteration") or 0),
            "eligible": ok,
            "reasons": reasons,
        })
        if ok:
            streak.append(record)
        else:
            streak = []
    promotable = len(streak) >= policy.min_consecutive_stable_iterations
    latest = ordered[-1] if ordered else {}
    return {
        "schema": "ai-ppt-plus/golden-promotion-evaluation/v1",
        "case_id": latest.get("case_id"),
        "promotable": promotable,
        "stable_streak": len(streak),
        "required_streak": policy.min_consecutive_stable_iterations,
        "candidate_iteration": int(latest.get("iteration") or 0) if promotable else None,
        "candidate_artifacts": dict(latest.get("artifacts") or {}) if promotable else {},
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
        "schema": "ai-ppt-plus/golden-baseline-manifest/v1",
        "version": str(version),
        "case_id": evaluation.get("case_id"),
        "source_iteration": evaluation.get("candidate_iteration"),
        "artifacts": dict(evaluation.get("candidate_artifacts") or {}),
        "previous_golden": previous_golden or None,
        "rollback_to_version": previous_version,
        "promotion_evidence": evaluation,
        "immutable": True,
    }
