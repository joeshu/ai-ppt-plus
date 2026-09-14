#!/usr/bin/env python3
"""Bounded retry policy for native image-generation asset repair.

The policy never switches to crop/source-reuse automatically. After the retry
budget is exhausted it stops at an explicit user-choice boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


FAILURE_HINTS = {
    "semantic": "Preserve the exact semantic subject and do not substitute a different symbol, object or concept.",
    "silhouette": "Match the source silhouette, proportions, negative space and outer contour more precisely.",
    "structure": "Preserve the source structure, part arrangement, orientation and relative geometry.",
    "color": "Match the source dominant colors, gradients, contrast and color-flow direction more closely.",
    "style": "Match the source visual style, stroke/fill language, depth, texture and rendering treatment.",
    "composition": "Match the source composition, subject placement, balance and internal spacing.",
    "detail": "Restore the source's distinctive local details while avoiding invented decoration.",
    "background": "Comply exactly with the requested transparent/key-color/opaque background mode.",
}

ISSUE_CODE_CATEGORIES = {
    "semantic_mismatch": ("semantic",),
    "silhouette_mismatch": ("silhouette", "structure"),
    "orientation_mismatch": ("structure",),
    "color_mismatch": ("color",),
    "gradient_flow_mismatch": ("color", "composition"),
    "style_mismatch": ("style",),
    "missing_detail": ("detail",),
    "extra_detail": ("detail",),
    "composition_mismatch": ("composition",),
    "background_noncompliance": ("background",),
}


@dataclass(frozen=True)
class AssetRetryPolicy:
    max_native_attempts: int = 3

    def __post_init__(self) -> None:
        if self.max_native_attempts < 1:
            raise ValueError("max_native_attempts must be >= 1")


def classify_reasons(reasons: list[str]) -> list[str]:
    """Legacy diagnostic helper; retry control no longer depends on free-form prose."""
    text = " ".join(reasons).casefold()
    categories: list[str] = []
    keyword_map = {
        "silhouette": ("silhouette", "outline", "contour", "shape"),
        "structure": ("structure", "proportion", "orientation", "geometry", "arrangement"),
        "color": ("color", "colour", "gradient", "contrast", "tone", "hue"),
        "style": ("style", "stroke", "texture", "rendering", "line weight", "fill"),
        "composition": ("composition", "placement", "spacing", "balance", "layout"),
        "detail": ("detail", "missing", "distinctive", "feature"),
    }
    for category, keywords in keyword_map.items():
        if any(keyword in text for keyword in keywords):
            categories.append(category)
    return categories or ["structure", "style"]


def categories_from_issue_codes(issue_codes: list[str]) -> list[str]:
    categories: list[str] = []
    for code in issue_codes:
        for category in ISSUE_CODE_CATEGORIES.get(code, ()):
            if category not in categories:
                categories.append(category)
    return categories or ["structure", "style"]


def strengthen_prompt(base_prompt: str | None, quality: dict[str, Any], *, attempt: int) -> str:
    prompt = (base_prompt or "Recreate the source asset faithfully.").strip()
    issue_codes = [str(item) for item in (quality.get("issue_codes") or []) if str(item).strip()]
    categories = categories_from_issue_codes(issue_codes)
    directives = [FAILURE_HINTS[item] for item in categories]
    scores = []
    for key in ("score", "structure_score", "style_score", "confidence"):
        if quality.get(key) is not None:
            scores.append(f"{key}={float(quality[key]):.3f}")
    controlled_failure = ", ".join(issue_codes) if issue_codes else "visual_fidelity_below_threshold"
    return (
        f"{prompt}\n\n"
        f"Native regeneration attempt {attempt}. Previous asset failed controlled QA checks: {controlled_failure}. "
        f"Observed QA: {', '.join(scores) if scores else 'no numeric scores'}.\n"
        + " ".join(directives)
        + " Keep the same semantic subject and do not add unrelated elements."
    )


def next_retry_request(request: dict[str, Any], quality: dict[str, Any], *, previous_attempts: int,
                       policy: AssetRetryPolicy | None = None) -> dict[str, Any]:
    policy = policy or AssetRetryPolicy()
    next_attempt = int(previous_attempts) + 1
    if next_attempt > policy.max_native_attempts:
        return {
            "object_id": request.get("object_id"),
            "status": "user-choice-required",
            "attempts_exhausted": previous_attempts,
            "max_native_attempts": policy.max_native_attempts,
            "choices": ["continue-native-generation", "crop-matting-fallback"],
            "reason": "native image-generation retry budget exhausted",
        }
    issue_codes = [str(item) for item in (quality.get("issue_codes") or []) if str(item).strip()]
    background_failure = "background_noncompliance" in issue_codes
    requested_mode = str(request.get("background_mode") or "transparent")
    generation_action = "regenerate"
    fallback_level = request.get("fallback_level", "direct-alpha")
    background_mode = requested_mode
    status = "retry-native-generation"
    if background_failure and requested_mode == "transparent" and next_attempt == 2:
        generation_action = "edit-to-transparent"
        fallback_level = "transparent-edit"
        status = "retry-native-image-edit"
    elif background_failure and requested_mode == "transparent" and next_attempt == 3:
        generation_action = "generate-chroma-fallback"
        fallback_level = "chroma-key"
        background_mode = str(request.get("chroma_fallback_mode") or "green")
        if background_mode not in {"green", "magenta", "red"}:
            raise ValueError("chroma_fallback_mode must be green, magenta or red")
        status = "retry-native-generation"
    failed_asset_ids = [str(item) for item in (quality.get("failed_asset_ids") or []) if str(item).strip()]
    retry_scope = "failed-assets-only" if failed_asset_ids else "single-asset"
    return {
        "object_id": request.get("object_id"),
        "status": status,
        "attempt": next_attempt,
        "max_native_attempts": policy.max_native_attempts,
        "generation_prompt": strengthen_prompt(request.get("generation_prompt"), quality, attempt=next_attempt),
        "generation_action": generation_action,
        "fallback_level": fallback_level,
        "background_mode": background_mode,
        "retry_scope": retry_scope,
        "failed_asset_ids": failed_asset_ids,
        "preserve_geometry": dict(request.get("preserve_geometry") or {}),
        "quality_failure": {
            "score": quality.get("score"),
            "structure_score": quality.get("structure_score"),
            "style_score": quality.get("style_score"),
            "confidence": quality.get("confidence"),
            "issue_codes": list(quality.get("issue_codes") or []),
            "reasons": list(quality.get("reasons") or []),
        },
    }
