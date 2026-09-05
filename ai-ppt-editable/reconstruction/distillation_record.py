#!/usr/bin/env python3
"""Build stable distillation evidence records from Astra reconstruction iterations."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class DistillationRecord:
    schema: str
    case_id: str
    iteration: int
    status: str
    accepted: bool
    resume_after_assets: bool
    allowed_object_ids: tuple[str, ...]
    repair_action_count: int
    repair_engine_counts: dict[str, int]
    pixel_fidelity_score: float | None
    pixel_fidelity_delta: float | None
    blocking_count: int
    blocking_delta: int | None
    native_editability_valid: bool
    semantic_accuracy: float | None
    semantic_audit: dict[str, Any] | None
    unauthorized_object_drift_count: int
    drift_objects: tuple[str, ...]
    rollback: bool
    rollback_reasons: tuple[str, ...]
    asset_retry_count: int
    asset_user_choice_required_count: int
    asset_resolved_count: int
    human_approved: bool | None
    artifacts: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _semantic_audit_snapshot(value: Any) -> dict[str, Any] | None:
    """Keep the bounded semantic evidence needed by promotion and audit tooling."""
    if not isinstance(value, dict):
        return None
    return {
        "valid": value.get("valid") is True,
        "accuracy": _float_or_none(value.get("accuracy")),
        "error_count": _int(value.get("error_count")) if value.get("error_count") is not None else None,
        "warning_count": _int(value.get("warning_count")) if value.get("warning_count") is not None else None,
        "expected_object_count": _int(value.get("expected_object_count")) if value.get("expected_object_count") is not None else None,
        "audited_object_count": _int(value.get("audited_object_count")) if value.get("audited_object_count") is not None else None,
    }


def build_distillation_record(*, iteration_record: dict[str, Any], asset_resolution: dict[str, Any] | None = None,
                              human_approved: bool | None = None) -> DistillationRecord:
    regression = iteration_record.get("regression") or {}
    drift = iteration_record.get("object_drift") or {}
    asset_resolution = asset_resolution or {}
    allowed = tuple(sorted(str(x) for x in (drift.get("allowed_object_ids") or iteration_record.get("allowed_object_ids") or []) if x))
    drift_objects = tuple(sorted(str(x) for x in (drift.get("unauthorized_objects") or []) if x))
    rollback_reasons = tuple(str(x) for x in (regression.get("reasons") or []) if x)
    semantic_audit = _semantic_audit_snapshot(iteration_record.get("semantic_audit"))
    semantic_accuracy = _float_or_none(iteration_record.get("semantic_accuracy"))
    if semantic_accuracy is None and semantic_audit is not None:
        semantic_accuracy = _float_or_none(semantic_audit.get("accuracy"))
    return DistillationRecord(
        schema="ai-ppt-plus/astra-distillation-record/v3",
        case_id=str(iteration_record.get("case_id") or ""),
        iteration=_int(iteration_record.get("iteration")),
        status=str(iteration_record.get("status") or "unknown"),
        accepted=iteration_record.get("accepted") is True,
        resume_after_assets=iteration_record.get("resume_after_assets") is True,
        allowed_object_ids=allowed,
        repair_action_count=_int(iteration_record.get("repair_action_count")),
        repair_engine_counts={str(k): _int(v) for k, v in (iteration_record.get("repair_engine_counts") or {}).items()},
        pixel_fidelity_score=_float_or_none(iteration_record.get("pixel_fidelity_score")),
        pixel_fidelity_delta=_float_or_none(regression.get("pixel_fidelity_delta")),
        blocking_count=_int(iteration_record.get("blocking_count")),
        blocking_delta=_int(regression.get("blocking_delta")) if regression.get("blocking_delta") is not None else None,
        native_editability_valid=iteration_record.get("native_editability_valid") is True,
        semantic_accuracy=semantic_accuracy,
        semantic_audit=semantic_audit,
        unauthorized_object_drift_count=_int(drift.get("unauthorized_drift_count")),
        drift_objects=drift_objects,
        rollback=regression.get("rollback") is True or iteration_record.get("status") == "rolled-back-regression",
        rollback_reasons=rollback_reasons,
        asset_retry_count=len(asset_resolution.get("retry_native_generation") or []),
        asset_user_choice_required_count=len(asset_resolution.get("user_choice_required") or []),
        asset_resolved_count=_int(asset_resolution.get("resolved_count")),
        human_approved=human_approved,
        artifacts=deepcopy(iteration_record.get("artifacts") or {}),
    )


def summarize_distillation(records: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [float(item["pixel_fidelity_score"]) for item in records if item.get("pixel_fidelity_score") is not None]
    semantic_scores = [float(item["semantic_accuracy"]) for item in records if item.get("semantic_accuracy") is not None]
    complete_semantic = 0
    for item in records:
        audit = item.get("semantic_audit")
        if not isinstance(audit, dict):
            continue
        expected = audit.get("expected_object_count")
        audited = audit.get("audited_object_count")
        if audit.get("valid") is True and audit.get("error_count") == 0 and expected is not None and audited == expected:
            complete_semantic += 1
    return {
        "schema": "ai-ppt-plus/astra-distillation-summary/v3",
        "record_count": len(records),
        "accepted_count": sum(1 for item in records if item.get("accepted") is True),
        "rollback_count": sum(1 for item in records if item.get("rollback") is True),
        "object_drift_rollback_count": sum(1 for item in records if int(item.get("unauthorized_object_drift_count") or 0) > 0),
        "asset_retry_count": sum(int(item.get("asset_retry_count") or 0) for item in records),
        "asset_user_choice_required_count": sum(int(item.get("asset_user_choice_required_count") or 0) for item in records),
        "repair_action_count": sum(int(item.get("repair_action_count") or 0) for item in records),
        "native_editability_failure_count": sum(1 for item in records if item.get("native_editability_valid") is not True),
        "semantic_perfect_count": sum(1 for item in records if item.get("semantic_accuracy") == 1.0),
        "semantic_evidence_complete_count": complete_semantic,
        "human_approved_count": sum(1 for item in records if item.get("human_approved") is True),
        "mean_pixel_fidelity_score": round(sum(scores) / len(scores), 6) if scores else None,
        "mean_semantic_accuracy": round(sum(semantic_scores) / len(semantic_scores), 6) if semantic_scores else None,
    }


def merge_performance_report(existing: dict[str, Any] | None, summary: dict[str, Any]) -> dict[str, Any]:
    report = deepcopy(existing or {})
    report.setdefault("schema", "ai-ppt-plus/performance-report/v1")
    report["astra_reconstruction"] = {
        "record_count": summary.get("record_count", 0),
        "accepted_count": summary.get("accepted_count", 0),
        "rollback_count": summary.get("rollback_count", 0),
        "object_drift_rollback_count": summary.get("object_drift_rollback_count", 0),
        "asset_retry_count": summary.get("asset_retry_count", 0),
        "asset_user_choice_required_count": summary.get("asset_user_choice_required_count", 0),
        "repair_action_count": summary.get("repair_action_count", 0),
        "native_editability_failure_count": summary.get("native_editability_failure_count", 0),
        "semantic_perfect_count": summary.get("semantic_perfect_count", 0),
        "semantic_evidence_complete_count": summary.get("semantic_evidence_complete_count", 0),
        "mean_pixel_fidelity_score": summary.get("mean_pixel_fidelity_score"),
        "mean_semantic_accuracy": summary.get("mean_semantic_accuracy"),
    }
    return report
