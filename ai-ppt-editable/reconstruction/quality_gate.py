#!/usr/bin/env python3
"""Deterministic correctness gate for reconstruction.

Visual similarity metrics are diagnostic evidence. Numeric visual thresholds
are never imposed unless an explicit project contract supplies them elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .difference_graph import DifferenceFinding, DifferenceGraph


@dataclass(frozen=True)
class GateResult:
    passed: bool
    failures: tuple[str, ...]
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QualityThresholds:
    editable_ratio: float = 0.98
    semantic_accuracy: float = 1.0
    allow_p1_findings: bool = False


class QualityGate:
    """Fail closed on deterministic correctness, not on arbitrary visual scores."""

    def __init__(self, thresholds: QualityThresholds | None = None) -> None:
        self.thresholds = thresholds or QualityThresholds()

    @staticmethod
    def _diagnostic_visual_finding(finding: DifferenceFinding) -> bool:
        evidence = finding.evidence if isinstance(finding.evidence, dict) else {}
        return (
            finding.object_id.startswith("slide:")
            and evidence.get("kind") == "pixel"
            and evidence.get("source") == "dual-comparison"
            and not finding.proposed_patch
        )

    def evaluate(
        self,
        *,
        differences: DifferenceGraph,
        global_visual_similarity: float,
        critical_region_scores: dict[str, float] | None = None,
        editable_ratio: float,
        semantic_accuracy: float,
        full_slide_raster_detected: bool,
        renderer_regressions: list[str] | None = None,
    ) -> GateResult:
        failures: list[str] = []
        t = self.thresholds
        regions = critical_region_scores or {}
        renderer_regressions = renderer_regressions or []

        if editable_ratio < t.editable_ratio:
            failures.append(f"editable ratio {editable_ratio:.4f} < {t.editable_ratio:.4f}")
        if semantic_accuracy < t.semantic_accuracy:
            failures.append(f"semantic accuracy {semantic_accuracy:.4f} < {t.semantic_accuracy:.4f}")
        if full_slide_raster_detected:
            failures.append("full-slide raster detected on editable route")
        if renderer_regressions:
            failures.extend(f"renderer regression: {item}" for item in renderer_regressions)

        blocking_levels = {"P0"}
        if not t.allow_p1_findings:
            blocking_levels.add("P1")
        for finding in differences.findings:
            if finding.severity in blocking_levels and not self._diagnostic_visual_finding(finding):
                failures.append(
                    f"{finding.severity} {finding.domain} finding {finding.id} on {finding.object_id}: {finding.message}"
                )

        return GateResult(
            passed=not failures,
            failures=tuple(failures),
            metrics={
                "global_visual_similarity": global_visual_similarity,
                "critical_region_scores": regions,
                "visual_metrics_diagnostic_only": True,
                "editable_ratio": editable_ratio,
                "semantic_accuracy": semantic_accuracy,
                "full_slide_raster_detected": full_slide_raster_detected,
                "renderer_regressions": renderer_regressions,
            },
        )
