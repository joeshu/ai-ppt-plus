#!/usr/bin/env python3
"""Closed-loop orchestration state for Astra + deterministic PPTX reconstruction."""
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
    GATE = "gate"
    COMPLETE = "complete"
    BLOCKED = "blocked"


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
    """Bounded orchestration shell.

    Model calls, rendering and concrete patch application are injected. This keeps
    execution deterministic and testable while allowing ChatGPT/Astra host runtimes
    to provide visual reasoning without coupling the repository to one API client.
    """

    def __init__(
        self,
        *,
        max_iterations: int = 4,
        repair_router: RepairRouter | None = None,
        quality_gate: QualityGate | None = None,
    ) -> None:
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
            )
            state.gate_result = gate

            if gate.passed:
                state.history.append(IterationRecord(
                    iteration=index,
                    difference_count=len(differences.findings),
                    blocking_count=len(differences.blocking()),
                    applied_actions=0,
                    deferred_actions=0,
                    gate_passed=True,
                    metrics=metrics,
                ))
                state.stage = Stage.COMPLETE
                state.artifacts["final"] = deck
                return state

            state.stage = Stage.REPAIR
            plan = self.repair_router.build_plan(differences)
            state.repair_plan = plan
            state.history.append(IterationRecord(
                iteration=index,
                difference_count=len(differences.findings),
                blocking_count=len(differences.blocking()),
                applied_actions=len(plan.actions),
                deferred_actions=len(plan.deferred),
                gate_passed=False,
                metrics=metrics,
            ))

            if plan.has_blocking_deferred or not plan.actions:
                state.stage = Stage.BLOCKED
                state.artifacts["blocked_candidate"] = deck
                return state

            deck = apply_repairs(deck, plan)
            state.artifacts[f"candidate_{index + 1}"] = deck

        state.stage = Stage.BLOCKED
        state.artifacts["blocked_candidate"] = deck
        return state
