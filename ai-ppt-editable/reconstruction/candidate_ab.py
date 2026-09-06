#!/usr/bin/env python3
"""Deterministic, fail-closed A/B gate for FTTR reconstruction candidates."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


SCHEMA = "ai-ppt-plus/fttr-candidate-ab/v1"
_REQUIRED_CONTEXT = (
    "source_sha256",
    "reference_sha256",
    "renderer",
    "renderer_version",
    "canvas",
    "font_profile_hash",
    "policy_version",
)
_REQUIRED_ASSET_PROVENANCE = (
    "asset_id",
    "target_region_id",
    "provider",
    "model",
    "prompt_sha256",
    "asset_sha256",
)


@dataclass(frozen=True)
class CandidateABPolicy:
    min_target_region_gain: float = 0.001
    max_global_regression: float = 0.002
    max_layout_regression: float = 0.002
    max_pixel_regression: float = 0.002
    max_mandatory_region_regression: float = 0.002
    required_semantic_accuracy: float = 1.0
    require_native_editability: bool = True
    require_zero_blockers: bool = True
    require_zero_drift: bool = True
    require_no_full_slide_raster: bool = True
    require_generated_asset_provenance: bool = True


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sha256(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _metrics(record: dict[str, Any]) -> dict[str, Any]:
    nested = record.get("metrics")
    return dict(nested) if isinstance(nested, dict) else record


def _context(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("comparison_context")
    return dict(value) if isinstance(value, dict) else {}


def _context_issues(baseline: dict[str, Any], candidate: dict[str, Any]) -> tuple[list[str], str | None]:
    reasons: list[str] = []
    base = _context(baseline)
    cand = _context(candidate)
    missing_base = [key for key in _REQUIRED_CONTEXT if base.get(key) in (None, "", {})]
    missing_cand = [key for key in _REQUIRED_CONTEXT if cand.get(key) in (None, "", {})]
    if missing_base:
        reasons.append("baseline_comparison_context_incomplete:" + ",".join(missing_base))
    if missing_cand:
        reasons.append("candidate_comparison_context_incomplete:" + ",".join(missing_cand))
    if not missing_base and not missing_cand and base != cand:
        reasons.append("comparison_context_mismatch")
    context_hash = _canonical_hash(base) if not reasons else None
    return reasons, context_hash


def _provenance_issues(candidate: dict[str, Any], policy: CandidateABPolicy) -> tuple[list[str], dict[str, Any]]:
    assets = candidate.get("generated_assets")
    if assets is None:
        assets = []
    reasons: list[str] = []
    valid_count = 0
    if not isinstance(assets, list):
        return ["generated_asset_provenance_invalid"], {"generated_asset_count": 0, "valid_count": 0, "bound": False}
    declared_count = _int(candidate.get("generated_asset_count"))
    if declared_count is not None and declared_count != len(assets):
        reasons.append("generated_asset_count_mismatch")
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            reasons.append(f"generated_asset_provenance_invalid:{index}")
            continue
        missing = [key for key in _REQUIRED_ASSET_PROVENANCE if not asset.get(key)]
        if missing:
            reasons.append(f"generated_asset_provenance_incomplete:{index}:" + ",".join(missing))
            continue
        if not _sha256(asset.get("prompt_sha256")) or not _sha256(asset.get("asset_sha256")):
            reasons.append(f"generated_asset_provenance_hash_invalid:{index}")
            continue
        valid_count += 1
    if policy.require_generated_asset_provenance and len(assets) != valid_count:
        reasons.append("generated_asset_provenance_not_complete")
    return reasons, {
        "generated_asset_count": len(assets),
        "valid_count": valid_count,
        "bound": not reasons,
    }


def _metric_delta(base_metrics: dict[str, Any], candidate_metrics: dict[str, Any], key: str) -> tuple[float | None, float | None, float | None]:
    base = _float(base_metrics.get(key))
    cand = _float(candidate_metrics.get(key))
    return base, cand, (cand - base) if base is not None and cand is not None else None


def evaluate_candidate_ab(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    target_region_ids: list[str] | tuple[str, ...],
    mandatory_region_ids: list[str] | tuple[str, ...] = (),
    policy: CandidateABPolicy | None = None,
) -> dict[str, Any]:
    """Return a deterministic v6-vs-v5 selection decision.

    Any missing comparison evidence, provenance gap, semantic/editability failure,
    or regression outside the configured budget selects the baseline and records
    an explicit rollback reason.
    """
    policy = policy or CandidateABPolicy()
    reasons: list[str] = []
    base_metrics = _metrics(baseline)
    cand_metrics = _metrics(candidate)
    target_ids = tuple(dict.fromkeys(str(x) for x in target_region_ids if str(x)))
    mandatory_ids = tuple(dict.fromkeys(str(x) for x in mandatory_region_ids if str(x)))

    base_case = str(baseline.get("case_id") or "")
    cand_case = str(candidate.get("case_id") or "")
    if not base_case or not cand_case or base_case != cand_case:
        reasons.append("case_id_mismatch")
    if baseline.get("accepted") is not True:
        reasons.append("baseline_not_accepted")
    if candidate.get("accepted") is not True:
        reasons.append("candidate_not_accepted")

    context_reasons, context_hash = _context_issues(baseline, candidate)
    reasons.extend(context_reasons)

    if policy.require_zero_blockers and int(candidate.get("blocking_count") or 0) != 0:
        reasons.append("candidate_blockers_present")
    if policy.require_native_editability and candidate.get("native_editability_valid") is not True:
        reasons.append("candidate_native_editability_invalid")
    if policy.require_zero_drift and int(candidate.get("unauthorized_object_drift_count") or 0) != 0:
        reasons.append("candidate_object_drift_present")
    if policy.require_no_full_slide_raster and bool(cand_metrics.get("full_slide_raster_detected", False)):
        reasons.append("candidate_full_slide_raster_detected")

    base_semantic = _float(baseline.get("semantic_accuracy"))
    cand_semantic = _float(candidate.get("semantic_accuracy"))
    if cand_semantic is None or cand_semantic != policy.required_semantic_accuracy:
        reasons.append("candidate_semantic_accuracy_not_perfect")
    if base_semantic is not None and cand_semantic is not None and cand_semantic < base_semantic:
        reasons.append("candidate_semantic_regression")

    metric_budgets = {
        "global_visual_similarity": policy.max_global_regression,
        "blurred_layout_ssim": policy.max_layout_regression,
        "pixel_fidelity_score": policy.max_pixel_regression,
    }
    metric_deltas: dict[str, Any] = {}
    for key, budget in metric_budgets.items():
        base, cand, delta = _metric_delta(base_metrics, cand_metrics, key)
        metric_deltas[key] = {"baseline": base, "candidate": cand, "delta": delta, "max_regression": budget}
        if base is None or cand is None:
            reasons.append(f"comparison_metric_missing:{key}")
        elif delta is not None and delta < -budget:
            reasons.append(f"comparison_metric_regressed:{key}")

    base_regions = base_metrics.get("critical_region_scores") if isinstance(base_metrics.get("critical_region_scores"), dict) else {}
    cand_regions = cand_metrics.get("critical_region_scores") if isinstance(cand_metrics.get("critical_region_scores"), dict) else {}
    target_deltas: dict[str, Any] = {}
    if not target_ids:
        reasons.append("target_regions_missing")
    for region_id in target_ids:
        base = _float(base_regions.get(region_id))
        cand = _float(cand_regions.get(region_id))
        delta = (cand - base) if base is not None and cand is not None else None
        target_deltas[region_id] = {"baseline": base, "candidate": cand, "delta": delta}
        if base is None or cand is None:
            reasons.append(f"target_region_evidence_missing:{region_id}")
        elif delta is None or delta < policy.min_target_region_gain:
            reasons.append(f"target_region_not_improved:{region_id}")

    mandatory_deltas: dict[str, Any] = {}
    for region_id in mandatory_ids:
        base = _float(base_regions.get(region_id))
        cand = _float(cand_regions.get(region_id))
        delta = (cand - base) if base is not None and cand is not None else None
        mandatory_deltas[region_id] = {"baseline": base, "candidate": cand, "delta": delta}
        if base is None or cand is None:
            reasons.append(f"mandatory_region_evidence_missing:{region_id}")
        elif delta is not None and delta < -policy.max_mandatory_region_regression:
            reasons.append(f"mandatory_region_regressed:{region_id}")

    provenance_reasons, provenance = _provenance_issues(candidate, policy)
    reasons.extend(provenance_reasons)

    accepted = not reasons
    baseline_variant = str(baseline.get("variant_id") or "baseline-v5")
    candidate_variant = str(candidate.get("variant_id") or "candidate-v6")
    winner = candidate_variant if accepted else baseline_variant
    selected_artifacts = dict((candidate if accepted else baseline).get("artifacts") or {})
    policy_dict = asdict(policy)
    replay_payload = {
        "schema": SCHEMA,
        "baseline": baseline,
        "candidate": candidate,
        "target_region_ids": list(target_ids),
        "mandatory_region_ids": list(mandatory_ids),
        "policy": policy_dict,
    }
    replay_digest = _canonical_hash(replay_payload)
    return {
        "schema": SCHEMA,
        "case_id": cand_case or base_case or None,
        "accepted": accepted,
        "decision": "promote-candidate" if accepted else "rollback-baseline",
        "winner_variant": winner,
        "rollback_to_baseline": not accepted,
        "reasons": reasons,
        "comparison_context_hash": context_hash,
        "metric_deltas": metric_deltas,
        "target_region_deltas": target_deltas,
        "mandatory_region_deltas": mandatory_deltas,
        "provenance": provenance,
        "selected_artifacts": selected_artifacts,
        "target_region_ids": list(target_ids),
        "mandatory_region_ids": list(mandatory_ids),
        "policy": policy_dict,
        "replay_digest": replay_digest,
    }


def verify_candidate_ab_replay(evaluation: dict[str, Any], baseline: dict[str, Any], candidate: dict[str, Any]) -> bool:
    if evaluation.get("schema") != SCHEMA:
        return False
    policy_raw = evaluation.get("policy")
    if not isinstance(policy_raw, dict):
        return False
    try:
        policy = CandidateABPolicy(**policy_raw)
    except TypeError:
        return False
    regenerated = evaluate_candidate_ab(
        baseline,
        candidate,
        target_region_ids=list(evaluation.get("target_region_ids") or []),
        mandatory_region_ids=list(evaluation.get("mandatory_region_ids") or []),
        policy=policy,
    )
    return regenerated == evaluation
