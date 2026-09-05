#!/usr/bin/env python3
"""Closed-loop orchestration state for Astra + deterministic PPTX reconstruction."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .difference_graph import DifferenceGraph
from .graph_ir import PageGraph
from .object_drift_guard import compare_object_drift
from .quality_gate import GateResult, QualityGate
from .repair_router import RepairPlan, RepairRouter
from .source_coverage import audit_source_coverage


class Stage(str, Enum):
    UNDERSTAND = "understand"
    AUTHOR = "author"
    RENDER = "render"
    QA = "qa"
    REPAIR = "repair"
    GATE = "gate"
    COMPLETE = "complete"
    BLOCKED = "blocked"
    EXTERNAL_ASSET = "external_asset"


@dataclass
class IterationRecord:
    iteration: int
    difference_count: int
    blocking_count: int
    applied_actions: int
    deferred_actions: int
    gate_passed: bool
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineState:
    stage: Stage = Stage.UNDERSTAND
    iteration: int = 0
    page_graph: PageGraph | None = None
    difference_graph: DifferenceGraph | None = None
    repair_plan: RepairPlan | None = None
    gate_result: GateResult | None = None
    history: list[IterationRecord] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)


class ReconstructionPipeline:
    """Bounded orchestration shell with fail-closed repair regression guards."""

    def __init__(self, *, max_iterations: int = 4, repair_router: RepairRouter | None = None, quality_gate: QualityGate | None = None) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        self.max_iterations = max_iterations
        self.repair_router = repair_router or RepairRouter()
        self.quality_gate = quality_gate or QualityGate()

    def run(
        self,
        *,
        understand: Callable[[], PageGraph],
        author: Callable[[PageGraph], Any],
        render: Callable[[Any], Any],
        inspect: Callable[[PageGraph, Any, Any], DifferenceGraph],
        apply_repairs: Callable[[Any, RepairPlan], Any],
        measure: Callable[[PageGraph, Any, Any, DifferenceGraph], dict[str, Any]],
        source_inventory: dict[str, Any] | None = None,
        extract_objects: Callable[[Any], dict[str, Any]] | None = None,
    ) -> PipelineState:
        state = PipelineState()
        state.page_graph = understand()
        strict_reference_profile = state.page_graph.metadata.get("route") == "reference-reconstruction"
        if source_inventory is not None or strict_reference_profile:
            coverage = audit_source_coverage(source_inventory or {}, state.page_graph)
            state.artifacts["source_coverage"] = coverage
            if not coverage["valid"] or extract_objects is None:
                state.stage = Stage.BLOCKED
                state.artifacts["coverage_blocker"] = "source coverage or PPTX extractor missing"
                return state
        state.stage = Stage.AUTHOR
        deck = author(state.page_graph)
        state.artifacts["candidate"] = deck
        passed_region_scores: dict[str, float] = {}

        for index in range(1, self.max_iterations + 1):
            state.iteration = index
            state.stage = Stage.RENDER
            rendered = render(deck)
            state.artifacts[f"render_{index}"] = rendered
            if source_inventory is not None:
                coverage = audit_source_coverage(source_inventory, state.page_graph, extract_objects(deck))
                state.artifacts[f"source_coverage_{index}"] = coverage
                if not coverage["valid"]:
                    state.stage = Stage.BLOCKED
                    state.artifacts["blocked_candidate"] = deck
                    return state

            state.stage = Stage.QA
            differences = inspect(state.page_graph, deck, rendered)
            state.difference_graph = differences
            metrics = measure(state.page_graph, deck, rendered, differences)
            region_scores = dict(metrics.get("critical_region_scores") or {})
            renderer_regressions = list(metrics.get("renderer_regressions") or [])
            threshold = self.quality_gate.thresholds.critical_region_similarity
            for region, previous in passed_region_scores.items():
                current = region_scores.get(region)
                if current is None:
                    renderer_regressions.append(f"previously accepted region missing after repair: {region}")
                elif current < threshold:
                    renderer_regressions.append(
                        f"previously accepted region regressed: {region} {previous:.4f} -> {current:.4f}"
                    )

            state.stage = Stage.GATE
            gate = self.quality_gate.evaluate(
                differences=differences,
                global_visual_similarity=float(metrics.get("global_visual_similarity", 0.0)),
                critical_region_scores=region_scores,
                required_critical_regions=list(metrics.get("required_critical_regions") or []),
                axis_scores=dict(metrics.get("axis_scores") or {}),
                strict_reference_profile=strict_reference_profile,
                editable_ratio=float(metrics.get("editable_ratio", 0.0)),
                semantic_accuracy=float(metrics.get("semantic_accuracy", 0.0)),
                full_slide_raster_detected=bool(metrics.get("full_slide_raster_detected", False)),
                renderer_regressions=renderer_regressions,
            )
            state.gate_result = gate
            for region, score in region_scores.items():
                if score >= threshold:
                    passed_region_scores[region] = max(score, passed_region_scores.get(region, 0.0))
            state.artifacts["passed_region_scores"] = dict(passed_region_scores)

            if gate.passed:
                state.history.append(IterationRecord(index, len(differences.findings), len(differences.blocking()), 0, 0, True, metrics))
                state.stage = Stage.COMPLETE
                state.artifacts["final"] = deck
                return state

            state.stage = Stage.REPAIR
            plan = self.repair_router.build_plan(differences)
            state.repair_plan = plan
            state.history.append(IterationRecord(
                index, len(differences.findings), len(differences.blocking()),
                len(plan.actions), len(plan.deferred), False, metrics,
            ))

            if plan.has_blocking_deferred or not plan.actions:
                state.stage = Stage.BLOCKED
                state.artifacts["blocked_candidate"] = deck
                return state

            before_repair = deck
            repair_result = apply_repairs(deck, plan)
            if isinstance(repair_result, dict) and "deck" in repair_result and "report" in repair_result:
                report = repair_result.get("report") if isinstance(repair_result.get("report"), dict) else {}
                state.artifacts[f"repair_report_{index}"] = report
                repaired_deck = repair_result["deck"]
                if report.get("requires_external_asset_generation"):
                    state.stage = Stage.EXTERNAL_ASSET
                    state.artifacts["asset_regeneration_requests"] = list(report.get("regeneration_requests") or [])
                    state.artifacts["blocked_candidate"] = repaired_deck
                    return state
                if report.get("valid") is False:
                    state.stage = Stage.BLOCKED
                    state.artifacts["blocked_candidate"] = repaired_deck
                    return state
            else:
                repaired_deck = repair_result

            allowed_ids = {action.object_id for action in plan.actions}
            drift = compare_object_drift(before_repair, repaired_deck, allowed_object_ids=allowed_ids)
            state.artifacts[f"repair_drift_{index}"] = drift
            if not drift["valid"]:
                state.stage = Stage.BLOCKED
                state.artifacts["blocked_candidate"] = repaired_deck
                state.artifacts["repair_drift_blocker"] = drift
                return state

            deck = repaired_deck
            state.artifacts[f"candidate_{index + 1}"] = deck

        state.stage = Stage.BLOCKED
        state.artifacts["blocked_candidate"] = deck
        return state
