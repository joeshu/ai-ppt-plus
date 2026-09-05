"""Versioned fidelity policy shared by reconstruction QA and release gates."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

POLICY_SCHEMA = "ai-ppt-plus/reconstruction-fidelity-policy/v1"
POLICY_VERSION = "2026.09-rf006"


@dataclass(frozen=True)
class FidelityPolicy:
    schema: str = POLICY_SCHEMA
    version: str = POLICY_VERSION
    global_visual_similarity: float = 0.94
    layout_similarity: float = 0.94
    typography_similarity: float = 0.95
    asset_similarity: float = 0.92
    critical_region_similarity: float = 0.92
    editable_ratio: float = 0.98
    semantic_accuracy: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def axis_thresholds(self) -> dict[str, float]:
        return {
            "layout": self.layout_similarity,
            "typography": self.typography_similarity,
            "asset": self.asset_similarity,
        }


DEFAULT_POLICY = FidelityPolicy()
