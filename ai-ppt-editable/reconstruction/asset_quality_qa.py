#!/usr/bin/env python3
"""Provider-neutral visual quality gate for externally generated assets.

File/background/hash validity is handled by asset_orchestrator. This module adds
an independent visual-semantic gate that compares a generated asset with the
immutable source-region evidence before the asset may resume PPTX authoring.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


ASSET_ISSUE_CODES = {
    "semantic_mismatch",
    "silhouette_mismatch",
    "orientation_mismatch",
    "color_mismatch",
    "gradient_flow_mismatch",
    "style_mismatch",
    "missing_detail",
    "extra_detail",
    "composition_mismatch",
    "background_noncompliance",
}


ASSET_QA_SYSTEM_INSTRUCTION = """You are the visual QA judge for one generated PPT asset.
Compare the immutable source-region image with the generated candidate asset.
Judge whether the candidate preserves the same visual subject, silhouette/structure,
major color relationships, style, orientation and required detail for its PPT role.
Do not judge surrounding slide layout. Do not suggest replacing the whole slide.
Return only JSON matching the asset-quality-response/v2 contract.
Use score, structure_score, style_score and confidence in [0,1].
Set approved=true only when the candidate is sufficiently faithful AND your confidence is high.
If rejected, provide issue_codes using only the allowed enum plus concise human-readable reasons.
issue_codes are machine-control signals; reasons are evidence only and must not control retry policy.
Set retry_native_generation=true only when another native generation attempt is appropriate.
For icons and simple decorative assets, structural fidelity matters more than pixel identity.
For gradients/complex artistic elements, composition and color-flow fidelity are required.
Allowed issue_codes: semantic_mismatch, silhouette_mismatch, orientation_mismatch, color_mismatch,
gradient_flow_mismatch, style_mismatch, missing_detail, extra_detail, composition_mismatch,
background_noncompliance.
"""


@dataclass(frozen=True)
class AssetQualityThresholds:
    min_score: float = 0.88
    min_structure_score: float = 0.90
    min_style_score: float = 0.84
    min_confidence: float = 0.82


@dataclass(frozen=True)
class AssetQualityRequest:
    task: str
    system_instruction: str
    payload: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps({
            "task": self.task,
            "system_instruction": self.system_instruction,
            "payload": self.payload,
        }, ensure_ascii=False, indent=2)


def build_asset_quality_request(*, object_id: str, source_region_id: str, generated_asset_id: str,
                                asset_kind: str | None = None, generation_prompt: str | None = None,
                                background_mode: str | None = None) -> AssetQualityRequest:
    if not object_id:
        raise ValueError("object_id is required")
    return AssetQualityRequest(
        task="asset-visual-qa",
        system_instruction=ASSET_QA_SYSTEM_INSTRUCTION,
        payload={
            "object_id": object_id,
            "source_region_id": source_region_id,
            "generated_asset_id": generated_asset_id,
            "asset_kind": asset_kind,
            "generation_prompt": generation_prompt,
            "background_mode": background_mode,
            "allowed_issue_codes": sorted(ASSET_ISSUE_CODES),
            "output_contract": "asset-quality-response/v2",
        },
    )


def parse_asset_quality_response(data: str | dict[str, Any], *, expected_object_id: str,
                                 thresholds: AssetQualityThresholds | None = None) -> dict[str, Any]:
    payload = json.loads(data) if isinstance(data, str) else dict(data)
    thresholds = thresholds or AssetQualityThresholds()
    object_id = str(payload.get("object_id") or "")
    if object_id != expected_object_id:
        raise ValueError("asset QA object_id mismatch")

    def score(name: str) -> float:
        value = float(payload.get(name, 0.0))
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be within [0,1]")
        return value

    overall = score("score")
    structure = score("structure_score")
    style = score("style_score")
    confidence = score("confidence")
    model_approved = payload.get("approved") is True

    reasons = payload.get("reasons") or []
    if not isinstance(reasons, list) or any(not isinstance(item, str) for item in reasons):
        raise ValueError("asset QA reasons must be a list of strings")

    issue_codes = payload.get("issue_codes") or []
    if not isinstance(issue_codes, list) or any(not isinstance(item, str) for item in issue_codes):
        raise ValueError("asset QA issue_codes must be a list of strings")
    unknown_codes = sorted(set(issue_codes) - ASSET_ISSUE_CODES)
    if unknown_codes:
        raise ValueError(f"asset QA issue_codes contain unsupported values: {', '.join(unknown_codes)}")
    issue_codes = list(dict.fromkeys(issue_codes))

    approved = (
        model_approved
        and overall >= thresholds.min_score
        and structure >= thresholds.min_structure_score
        and style >= thresholds.min_style_score
        and confidence >= thresholds.min_confidence
        and not issue_codes
    )

    retry_native_generation = bool(payload.get("retry_native_generation", not approved))
    if confidence < thresholds.min_confidence:
        approved = False
        retry_native_generation = False

    return {
        "schema": "ai-ppt-plus/asset-quality-evaluation/v2",
        "object_id": object_id,
        "approved": approved,
        "model_approved": model_approved,
        "score": overall,
        "structure_score": structure,
        "style_score": style,
        "confidence": confidence,
        "issue_codes": issue_codes,
        "reasons": reasons,
        "retry_native_generation": retry_native_generation,
        "thresholds": {
            "min_score": thresholds.min_score,
            "min_structure_score": thresholds.min_structure_score,
            "min_style_score": thresholds.min_style_score,
            "min_confidence": thresholds.min_confidence,
        },
    }
