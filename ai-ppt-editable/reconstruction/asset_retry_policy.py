#!/usr/bin/env python3
"""Bounded retry policy for native image-generation asset repair.

The policy never switches to crop/source-reuse automatically. After the retry
budget is exhausted it stops at an explicit user-choice boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


FAILURE_HINTS = {
    "silhouette": "Match the source silhouette, proportions, negative space and outer contour more precisely.",
    "structure": "Preserve the source structure, part arrangement, orientation and relative geometry.",
    "color": "Match the source dominant colors, gradients, contrast and color-flow direction more closely.",
    "style": "Match the source visual style, stroke/fill language, depth, texture and rendering treatment.",
    "composition": "Match the source composition, subject placement, balance and internal spacing.",
    "detail": "Restore the source's distinctive local details while avoiding invented decoration.",
}


@dataclass(frozen=True)
class AssetRetryPolicy:
    max_native_attempts: int = 3

    def __post_init__(self) -> None:
        if self.max_native_attempts < 1:
            raise ValueError("max_native_attempts must be >= 1")


def classify_reasons(reasons: list[str]) -> list[str]:
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


def strengthen_prompt(base_prompt: str | None, quality: dict[str, Any], *, attempt: int) -> str:
    prompt = (base_prompt or "Recreate the source asset faithfully.").strip()
    reasons = [str(item) for item in (quality.get("reasons") or []) if str(item).strip()]
    categories = classify_reasons(reasons)
    directives = [FAILURE_HINTS[item] for item in categories]
    scores = []
    for key in ("score", "structure_score", "style_score"):
        if quality.get(key) is not None:
            scores.append(f"{key}={float(quality[key]):.3f}")
    reason_text = "; ".join(reasons) if reasons else "visual fidelity below threshold"
    return (
        f"{prompt}\n\n"
        f"Native regeneration attempt {attempt}. Previous asset was rejected: {reason_text}. "
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
    return {
        "object_id": request.get("object_id"),
        "status": "retry-native-generation",
        "attempt": next_attempt,
        "max_native_attempts": policy.max_native_attempts,
        "generation_prompt": strengthen_prompt(request.get("generation_prompt"), quality, attempt=next_attempt),
        "background_mode": request.get("background_mode", "transparent"),
        "preserve_geometry": dict(request.get("preserve_geometry") or {}),
        "quality_failure": {
            "score": quality.get("score"),
            "structure_score": quality.get("structure_score"),
            "style_score": quality.get("style_score"),
            "reasons": list(quality.get("reasons") or []),
        },
    }
