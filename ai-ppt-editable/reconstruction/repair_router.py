#!/usr/bin/env python3
"""Route DifferenceGraph findings to bounded deterministic repair engines."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .difference_graph import DifferenceFinding, DifferenceGraph


SAFE_PATCH_KEYS = {
    "geometry": {"x", "y", "w", "h", "rotation", "crop", "radius", "padding", "gap"},
    "typography": {"font", "font_size", "bold", "italic", "color", "line_spacing", "paragraph_spacing", "margin", "autofit", "runs"},
    "asset": {"scale", "crop", "rotation", "opacity", "regenerate", "generation_prompt", "background_mode"},
    "hierarchy": {"group_children", "connector_targets"},
    "semantic": {"target_type", "native_required", "table_data", "chart_data", "group_children", "connector_targets"},
}

ENGINE_BY_DOMAIN = {
    "geometry": "geometry_repair",
    "typography": "typography_repair",
    "asset": "asset_repair",
    "hierarchy": "semantic_repair",
    "semantic": "semantic_repair",
}


@dataclass(frozen=True)
class RepairAction:
    finding_id: str
    object_id: str
    engine: str
    patch: dict[str, Any]
    severity: str
    confidence: float
    requires_regeneration: bool = False
    requires_human_review: bool = False
    reason: str = ""


@dataclass(frozen=True)
class RepairPlan:
    actions: tuple[RepairAction, ...]
    deferred: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def has_blocking_deferred(self) -> bool:
        return any(item.get("severity") in {"P0", "P1"} and not item.get("diagnostic_only", False) for item in self.deferred)

    def by_engine(self, engine: str) -> tuple[RepairAction, ...]:
        return tuple(action for action in self.actions if action.engine == engine)


class RepairRouter:
    def __init__(self, *, min_auto_confidence: float = 0.82) -> None:
        self.min_auto_confidence = float(min_auto_confidence)

    def _sanitize_patch(self, finding: DifferenceFinding) -> tuple[dict[str, Any], list[str]]:
        allowed = SAFE_PATCH_KEYS[finding.domain]
        accepted, rejected = {}, []
        for key, value in finding.proposed_patch.items():
            (accepted if key in allowed else rejected).append(key) if False else None
            if key in allowed:
                accepted[key] = value
            else:
                rejected.append(key)
        return accepted, rejected

    @staticmethod
    def _diagnostic_only(finding: DifferenceFinding) -> bool:
        evidence = finding.evidence if isinstance(finding.evidence, dict) else {}
        return finding.object_id.startswith("slide:") and evidence.get("kind") == "pixel" and evidence.get("source") == "dual-comparison" and not finding.proposed_patch

    def build_plan(self, graph: DifferenceGraph) -> RepairPlan:
        actions, deferred = [], []
        for finding in graph.findings:
            patch, rejected = self._sanitize_patch(finding)
            low_confidence = finding.confidence < self.min_auto_confidence
            no_patch = not patch
            semantic_risk = finding.domain == "semantic" and finding.severity == "P0"
            diagnostic_only = self._diagnostic_only(finding)
            if low_confidence or no_patch or rejected or semantic_risk:
                deferred.append({"finding_id": finding.id, "object_id": finding.object_id, "domain": finding.domain,
                                 "severity": finding.severity, "confidence": finding.confidence,
                                 "reason": "diagnostic-only" if diagnostic_only else "low-confidence" if low_confidence else "unsafe-or-incomplete-patch",
                                 "diagnostic_only": diagnostic_only, "rejected_patch_keys": rejected, "proposed_patch": finding.proposed_patch})
                continue
            actions.append(RepairAction(finding_id=finding.id, object_id=finding.object_id,
                                        engine=ENGINE_BY_DOMAIN[finding.domain], patch=patch,
                                        severity=finding.severity, confidence=finding.confidence,
                                        requires_regeneration=(finding.domain == "asset" and bool(patch.get("regenerate"))),
                                        reason=finding.message))
        return RepairPlan(actions=tuple(actions), deferred=tuple(deferred))
