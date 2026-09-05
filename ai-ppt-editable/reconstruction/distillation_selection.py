#!/usr/bin/env python3
"""Select positive and hard-negative samples from Astra distillation records."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DistillationSelectionPolicy:
    min_visual_delta: float = 0.0
    required_semantic_accuracy: float = 1.0
    require_human_approval: bool = True
    require_native_editability: bool = True
    require_semantic_accuracy: bool = True
    require_zero_drift: bool = True
    require_no_rollback: bool = True


def _bool(record: dict[str, Any], key: str, default: bool = False) -> bool:
    value = record.get(key, default)
    return value is True


def _float(record: dict[str, Any], key: str) -> float | None:
    value = record.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(record: dict[str, Any], key: str) -> int:
    try:
        return int(record.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def classify_record(record: dict[str, Any], *, policy: DistillationSelectionPolicy | None = None) -> dict[str, Any]:
    policy = policy or DistillationSelectionPolicy()
    reasons: list[str] = []
    negative_reasons: list[str] = []

    accepted = _bool(record, "accepted")
    rollback = _bool(record, "rollback") or str(record.get("status") or "").startswith("rolled-back")
    native_evidence_present = "native_editability_valid" in record
    native_valid = record.get("native_editability_valid") is True
    semantic = _float(record, "semantic_accuracy")
    drift_count = _int(record, "unauthorized_object_drift_count")
    visual_delta = _float(record, "pixel_fidelity_delta")
    human_approved = record.get("human_approved") is True
    user_choice_required = (
        record.get("asset_user_choice_required") is True
        or _int(record, "asset_user_choice_required_count") > 0
    )

    if rollback:
        negative_reasons.append("rollback")
        regression = record.get("rollback_reasons") or []
        for reason in regression:
            negative_reasons.append(f"rollback:{reason}")
    if drift_count > 0:
        negative_reasons.append("unauthorized_object_drift")
    if native_evidence_present and not native_valid:
        negative_reasons.append("native_editability_failure")
    if semantic is not None and semantic != policy.required_semantic_accuracy:
        negative_reasons.append("semantic_accuracy_failure")
    if visual_delta is not None and visual_delta < 0:
        negative_reasons.append("visual_regression")
    if user_choice_required:
        negative_reasons.append("asset_retry_exhausted")

    hard_negative = bool(negative_reasons)

    if not accepted:
        reasons.append("not_accepted")
    if policy.require_no_rollback and rollback:
        reasons.append("rollback_present")
    if policy.require_zero_drift and drift_count > 0:
        reasons.append("object_drift_present")
    if policy.require_native_editability:
        if not native_evidence_present:
            reasons.append("native_editability_evidence_missing")
        elif not native_valid:
            reasons.append("native_editability_invalid")
    if policy.require_semantic_accuracy:
        if semantic is None:
            reasons.append("semantic_accuracy_missing")
        elif semantic != policy.required_semantic_accuracy:
            reasons.append("semantic_accuracy_not_perfect")
    if visual_delta is None:
        reasons.append("missing_visual_delta")
    elif visual_delta <= policy.min_visual_delta:
        reasons.append("visual_not_improved")
    if policy.require_human_approval and not human_approved:
        reasons.append("human_approval_missing")
    if user_choice_required:
        reasons.append("asset_user_choice_required")

    positive = not reasons
    if positive:
        reasons = ["accepted_no_drift_visual_improved_semantic_perfect_native_valid_human_approved"]

    return {
        "schema": "ai-ppt-plus/distillation-selection/v2",
        "case_id": record.get("case_id"),
        "iteration": record.get("iteration"),
        "positive": positive,
        "hard_negative": hard_negative,
        "selection_reasons": reasons,
        "negative_reasons": negative_reasons,
        "metrics": {
            "pixel_fidelity_score": record.get("pixel_fidelity_score"),
            "pixel_fidelity_delta": visual_delta,
            "semantic_accuracy": semantic,
            "blocking_count": record.get("blocking_count"),
            "unauthorized_object_drift_count": drift_count,
            "asset_user_choice_required_count": _int(record, "asset_user_choice_required_count"),
        },
        "record": record,
    }


def select_records(records: list[dict[str, Any]], *, policy: DistillationSelectionPolicy | None = None) -> dict[str, Any]:
    classified = [classify_record(record, policy=policy) for record in records]
    positives = [item for item in classified if item["positive"]]
    hard_negatives = [item for item in classified if item["hard_negative"]]
    rejected = [item for item in classified if not item["positive"] and not item["hard_negative"]]
    return {
        "schema": "ai-ppt-plus/distillation-selection-batch/v2",
        "positive_count": len(positives),
        "hard_negative_count": len(hard_negatives),
        "rejected_count": len(rejected),
        "positives": positives,
        "hard_negatives": hard_negatives,
        "rejected": rejected,
    }
