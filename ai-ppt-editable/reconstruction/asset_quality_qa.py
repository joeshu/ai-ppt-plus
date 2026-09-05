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


ASSET_QA_SYSTEM_INSTRUCTION = """You are the visual QA judge for one generated PPT asset.
Compare the immutable source-region image with the generated candidate asset.
Judge whether the candidate preserves the same visual subject, silhouette/structure,
major color relationships, style, orientation and required detail for its PPT role.
Do not judge surrounding slide layout. Do not suggest replacing the whole slide.
Return only JSON matching the asset-quality-response contract.
Use score in [0,1]. Set approved=true only when the candidate is sufficiently faithful.
If rejected, identify concise reasons and whether another native image-generation retry is appropriate.
For icons and simple decorative assets, structural fidelity matters more than pixel identity.
For gradients/complex artistic elements, composition and color-flow fidelity are required.
"""


@dataclass(frozen=True)
class AssetQualityThresholds:
    min_score: float = 0.88
    min_structure_score: float = 0.90
    min_style_score: float = 0.84


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
            "output_contract": "asset-quality-response/v1",
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
    model_approved = payload.get("approved") is True
    reasons = payload.get("reasons") or []
    if not isinstance(reasons, list) or any(not isinstance(item, str) for item in reasons):
        raise ValueError("asset QA reasons must be a list of strings")
    approved = (
        model_approved
        and overall >= thresholds.min_score
        and structure >= thresholds.min_structure_score
        and style >= thresholds.min_style_score
    )
    return {
        "schema": "ai-ppt-plus/asset-quality-evaluation/v1",
        "object_id": object_id,
        "approved": approved,
        "model_approved": model_approved,
        "score": overall,
        "structure_score": structure,
        "style_score": style,
        "reasons": reasons,
        "retry_native_generation": bool(payload.get("retry_native_generation", not approved)),
        "thresholds": {
            "min_score": thresholds.min_score,
            "min_structure_score": thresholds.min_structure_score,
            "min_style_score": thresholds.min_style_score,
        },
    }
