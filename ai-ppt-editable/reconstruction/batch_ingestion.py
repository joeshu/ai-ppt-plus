#!/usr/bin/env python3
"""Strict ingestion of Astra visual-QA results into bounded repair iterations."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .difference_graph import DifferenceGraph
from .evidence_bridge import merge_difference_graphs
from .graph_ir import PageGraph
from .repair_router import RepairPlan, RepairRouter


class AstraIngestionError(ValueError):
    pass


def validate_astra_object_ids(page_graph: PageGraph, astra_graph: DifferenceGraph) -> None:
    known = {node.id for node in page_graph.nodes}
    unknown = sorted({item.object_id for item in astra_graph.findings if item.object_id not in known})
    if unknown:
        raise AstraIngestionError("Astra DifferenceGraph references unknown object ids: " + ", ".join(unknown))


def ingest_astra_qa(
    *,
    page_graph: PageGraph,
    deterministic_graph: DifferenceGraph,
    astra_graph: DifferenceGraph,
    router: RepairRouter | None = None,
) -> dict[str, Any]:
    """Validate, merge and route one Astra QA response.

    Deterministic evidence remains authoritative. Astra may add object-local
    diagnosis and bounded patches but cannot delete or weaken deterministic
    blockers.
    """
    validate_astra_object_ids(page_graph, astra_graph)
    merged = merge_difference_graphs(deterministic_graph, astra_graph)
    plan = (router or RepairRouter()).build_plan(merged)
    return {
        "merged_difference_graph": asdict(merged),
        "repair_plan": {
            "actions": [asdict(item) for item in plan.actions],
            "deferred": [dict(item) for item in plan.deferred],
            "has_blocking_deferred": plan.has_blocking_deferred,
        },
        "summary": summarize_iteration(merged, plan),
    }


def summarize_iteration(graph: DifferenceGraph, plan: RepairPlan) -> dict[str, Any]:
    severity_counts = {severity: sum(1 for item in graph.findings if item.severity == severity) for severity in ("P0", "P1", "P2", "P3")}
    domain_counts = {domain: sum(1 for item in graph.findings if item.domain == domain) for domain in ("geometry", "typography", "asset", "semantic")}
    engine_counts = {
        engine: sum(1 for item in plan.actions if item.engine == engine)
        for engine in ("geometry_repair", "typography_repair", "asset_repair", "semantic_repair")
    }
    return {
        "difference_count": len(graph.findings),
        "blocking_count": len(graph.blocking()),
        "severity_counts": severity_counts,
        "domain_counts": domain_counts,
        "repair_action_count": len(plan.actions),
        "repair_engine_counts": engine_counts,
        "deferred_count": len(plan.deferred),
        "blocking_deferred": plan.has_blocking_deferred,
        "requires_external_asset": any(item.requires_regeneration for item in plan.actions),
    }


def convergence_delta(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Measure whether the current iteration actually converged."""
    previous_visual = float(previous.get("pixel_fidelity_score", 0.0))
    current_visual = float(current.get("pixel_fidelity_score", 0.0))
    previous_blocking = int(previous.get("blocking_count", 0))
    current_blocking = int(current.get("blocking_count", 0))
    return {
        "pixel_fidelity_delta": round(current_visual - previous_visual, 6),
        "blocking_delta": current_blocking - previous_blocking,
        "visual_improved": current_visual > previous_visual,
        "blocking_improved": current_blocking < previous_blocking,
        "regressed": current_visual < previous_visual or current_blocking > previous_blocking,
    }
