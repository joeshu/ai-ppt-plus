#!/usr/bin/env python3
"""Multi-axis quality gate for visual reconstruction delivery."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from math import isfinite

from .difference_graph import DifferenceGraph


def _valid_unit_interval(value: Any) -> bool:
    """Return whether a metric is a real finite number in [0, 1]."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return isfinite(numeric) and 0 <= numeric <= 1


@dataclass(frozen=True)
class GateResult:
    passed: bool
    failures: tuple[str, ...]
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QualityThresholds:
    global_visual_similarity: float = 0.94
    critical_region_similarity: float = 0.92
    editable_ratio: float = 0.98
    semantic_accuracy: float = 1.0
    allow_p1_findings: bool = False


class QualityGate:
    """Fail closed on visual, editability, semantic, and structural regressions."""

    def __init__(self, thresholds: QualityThresholds | None = None) -> None:
        self.thresholds = thresholds or QualityThresholds()

    def evaluate(
        self,
        *,
        differences: DifferenceGraph,
        global_visual_similarity: float,
        critical_region_scores: dict[str, float] | None = None,
        required_critical_regions: list[str] | tuple[str, ...] | None = None,
        editable_ratio: float,
        semantic_accuracy: float,
        full_slide_raster_detected: bool,
        renderer_regressions: list[str] | None = None,
    ) -> GateResult:
        failures: list[str] = []
        t = self.thresholds
        regions = critical_region_scores or {}
        required_regions = tuple(required_critical_regions or ())
        renderer_regressions = renderer_regressions or []

        metric_values = {"global_visual_similarity": global_visual_similarity,
                         "editable_ratio": editable_ratio,
                         "semantic_accuracy": semantic_accuracy,
                         **{f"region:{name}": score for name, score in regions.items()}}
        invalid_metrics = set()
        for name, value in metric_values.items():
            if not _valid_unit_interval(value):
                failures.append(f"invalid quality metric: {name}")
                invalid_metrics.add(name)

        missing_regions = sorted(set(required_regions) - set(regions))
        if missing_regions:
            failures.append("missing critical region scores: " + ", ".join(missing_regions))

        if "global_visual_similarity" not in invalid_metrics and global_visual_similarity < t.global_visual_similarity:
            failures.append(
                f"global visual similarity {global_visual_similarity:.4f} < {t.global_visual_similarity:.4f}"
            )
        for region, score in regions.items():
            if f"region:{region}" not in invalid_metrics and score < t.critical_region_similarity:
                failures.append(
                    f"critical region {region} similarity {score:.4f} < {t.critical_region_similarity:.4f}"
                )
        if "editable_ratio" not in invalid_metrics and editable_ratio < t.editable_ratio:
            failures.append(f"editable ratio {editable_ratio:.4f} < {t.editable_ratio:.4f}")
        if "semantic_accuracy" not in invalid_metrics and semantic_accuracy < t.semantic_accuracy:
            failures.append(f"semantic accuracy {semantic_accuracy:.4f} < {t.semantic_accuracy:.4f}")
        if full_slide_raster_detected:
            failures.append("full-slide raster detected on editable route")
        if renderer_regressions:
            failures.extend(f"renderer regression: {item}" for item in renderer_regressions)

        blocking_levels = {"P0"}
        if not t.allow_p1_findings:
            blocking_levels.add("P1")
        for finding in differences.findings:
            if finding.severity in blocking_levels:
                failures.append(
                    f"{finding.severity} {finding.domain} finding {finding.id} on {finding.object_id}: {finding.message}"
                )

        return GateResult(
            passed=not failures,
            failures=tuple(failures),
            metrics={
                "global_visual_similarity": global_visual_similarity,
                "critical_region_scores": regions,
                "required_critical_regions": list(required_regions),
                "editable_ratio": editable_ratio,
                "semantic_accuracy": semantic_accuracy,
                "full_slide_raster_detected": full_slide_raster_detected,
                "renderer_regressions": renderer_regressions,
            },
        )
