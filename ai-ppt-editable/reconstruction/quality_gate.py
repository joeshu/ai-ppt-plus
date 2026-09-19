#!/usr/bin/env python3
"""Correctness gate plus Golden visual target assessment for reconstruction."""
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
    # These are Golden/release-quality targets, not per-iteration authoring blockers.
    global_visual_similarity: float = 0.90
    critical_region_similarity: float = 0.90
    editable_ratio: float = 0.98
    semantic_accuracy: float = 1.0
    allow_p1_findings: bool = False


class QualityGate:
    """Fail closed on deterministic correctness; assess visual targets separately."""

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

    def _visual_target_failures(
        self,
        global_visual_similarity: float,
        critical_region_scores: dict[str, float],
    ) -> list[str]:
        failures: list[str] = []
        t = self.thresholds
        if global_visual_similarity < t.global_visual_similarity:
            failures.append(
                f"global visual similarity {global_visual_similarity:.4f} < {t.global_visual_similarity:.4f}"
            )
        for region, score in critical_region_scores.items():
            if score < t.critical_region_similarity:
                failures.append(
                    f"critical region {region} similarity {score:.4f} < {t.critical_region_similarity:.4f}"
                )
        return failures

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
        require_golden: bool = False,
    ) -> GateResult:
        failures: list[str] = []
        t = self.thresholds
        regions = critical_region_scores or {}
        renderer_regressions = renderer_regressions or []
        visual_failures = self._visual_target_failures(global_visual_similarity, regions)

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

        if require_golden:
            failures.extend(f"Golden target: {item}" for item in visual_failures)

        return GateResult(
            passed=not failures,
            failures=tuple(failures),
            metrics={
                "global_visual_similarity": global_visual_similarity,
                "critical_region_scores": regions,
                "golden_visual_ready": not visual_failures,
                "golden_visual_failures": tuple(visual_failures),
                "golden_required": bool(require_golden),
                "editable_ratio": editable_ratio,
                "semantic_accuracy": semantic_accuracy,
                "full_slide_raster_detected": full_slide_raster_detected,
                "renderer_regressions": renderer_regressions,
            },
        )
