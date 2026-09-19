#!/usr/bin/env python3
"""Render-driven reconstruction orchestration with explicit human/agent review state."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from .difference_graph import DifferenceGraph
from .graph_ir import PageGraph
from .quality_gate import GateResult, QualityGate
from .repair_router import RepairPlan, RepairRouter


class Stage(str, Enum):
    UNDERSTAND = "understand"
    AUTHOR = "author"
    RENDER = "render"
    QA = "qa"
    REPAIR = "repair"
    REVIEW = "review"
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
    """Bounded render -> inspect -> repair loop.

    Deterministic correctness remains fail-closed. Visual targets are Golden
    promotion criteria. When a fresh render is below target but there is no
    safe deterministic patch, the pipeline returns REVIEW with a valid draft
    instead of mislabeling the deck complete or blocking further visual review.
    """

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
    ) -> PipelineState:
        state = PipelineState()
        state.page_graph = understand()
        state.stage = Stage.AUTHOR
        deck = author(state.page_graph)
        state.artifacts["candidate"] = deck

        for index in range(1, self.max_iterations + 1):
            state.iteration = index
            state.stage = Stage.RENDER
            rendered = render(deck)
            state.artifacts[f"render_{index}"] = rendered

            state.stage = Stage.QA
            differences = inspect(state.page_graph, deck, rendered)
            state.difference_graph = differences
            metrics = measure(state.page_graph, deck, rendered, differences)

            state.stage = Stage.GATE
            gate = self.quality_gate.evaluate(
                differences=differences,
                global_visual_similarity=float(metrics.get("global_visual_similarity", 0.0)),
                critical_region_scores=dict(metrics.get("critical_region_scores") or {}),
                editable_ratio=float(metrics.get("editable_ratio", 0.0)),
                semantic_accuracy=float(metrics.get("semantic_accuracy", 0.0)),
                full_slide_raster_detected=bool(metrics.get("full_slide_raster_detected", False)),
                renderer_regressions=list(metrics.get("renderer_regressions") or []),
                require_golden=False,
            )
            state.gate_result = gate
            metrics = dict(metrics)
            metrics["golden_visual_ready"] = bool(gate.metrics.get("golden_visual_ready"))
            metrics["golden_visual_failures"] = list(gate.metrics.get("golden_visual_failures") or [])

            state.stage = Stage.REPAIR
            plan = self.repair_router.build_plan(differences)
            state.repair_plan = plan

            if plan.actions:
                state.history.append(IterationRecord(
                    index, len(differences.findings), len(differences.blocking()),
                    len(plan.actions), len(plan.deferred), gate.passed, metrics,
                ))
                repair_result = apply_repairs(deck, plan)
                if isinstance(repair_result, dict) and "deck" in repair_result and "report" in repair_result:
                    report = repair_result.get("report") if isinstance(repair_result.get("report"), dict) else {}
                    state.artifacts[f"repair_report_{index}"] = report
                    deck = repair_result["deck"]
                    if report.get("requires_external_asset_generation"):
                        state.stage = Stage.EXTERNAL_ASSET
                        state.artifacts["asset_regeneration_requests"] = list(report.get("regeneration_requests") or [])
                        state.artifacts["blocked_candidate"] = deck
                        return state
                    if report.get("valid") is False:
                        state.stage = Stage.BLOCKED
                        state.artifacts["blocked_candidate"] = deck
                        return state
                else:
                    deck = repair_result
                state.artifacts[f"candidate_{index + 1}"] = deck
                continue

            state.history.append(IterationRecord(
                index, len(differences.findings), len(differences.blocking()),
                0, len(plan.deferred), gate.passed, metrics,
            ))

            if not gate.passed:
                state.stage = Stage.BLOCKED
                state.artifacts["blocked_candidate"] = deck
                state.artifacts["blocking_failures"] = list(gate.failures)
                return state

            if plan.deferred or not gate.metrics.get("golden_visual_ready", False):
                state.stage = Stage.REVIEW
                state.artifacts["draft_candidate"] = deck
                state.artifacts["review_reason"] = (
                    "visual-target-not-yet-golden"
                    if not gate.metrics.get("golden_visual_ready", False)
                    else "deferred-findings-require-review"
                )
                state.artifacts["deferred_findings"] = [dict(item) for item in plan.deferred]
                return state

            state.stage = Stage.COMPLETE
            state.artifacts["final"] = deck
            return state

        state.stage = Stage.REVIEW if state.gate_result and state.gate_result.passed else Stage.BLOCKED
        state.artifacts["draft_candidate" if state.stage == Stage.REVIEW else "blocked_candidate"] = deck
        state.artifacts["review_reason"] = "iteration-budget-exhausted" if state.stage == Stage.REVIEW else "correctness-gate-failed"
        return state
