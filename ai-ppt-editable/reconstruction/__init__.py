"""Astra visual reconstruction contracts, evidence fusion and repair routing."""

from .graph_ir import PageGraph, GraphValidationError
from .difference_graph import DifferenceGraph
from .repair_router import RepairRouter, RepairPlan
from .quality_gate import QualityGate, QualityThresholds, GateResult
from .quality_policy import FidelityPolicy, DEFAULT_POLICY, POLICY_VERSION
from .pipeline import ReconstructionPipeline, PipelineState, Stage
from .manifest_bridge import build_page_graph
from .repair_executors import RepairExecutionError, execute_action, execute_plan
from .source_coverage import audit_source_coverage, extract_pptx_objects
from .typography_search import calibrate_typography, measurement_loss
from .text_target_spec import build_text_target_spec
from .relation_geometry import solve_peer_layout, solve_graph_relations
from .asset_subject import subject_placement
from .asset_metrics import compare_asset_subjects
from .evidence_bridge import EvidenceThresholds, from_dual_comparison, merge_difference_graphs
from .batch_ingestion import AstraIngestionError, validate_astra_object_ids, ingest_astra_qa, summarize_iteration, convergence_delta
from .astra_contract import (
    AstraRequest,
    build_reconstruction_request,
    build_visual_qa_request,
    parse_reconstruction_response,
    parse_visual_qa_response,
)

__all__ = [
    "PageGraph",
    "GraphValidationError",
    "DifferenceGraph",
    "RepairRouter",
    "RepairPlan",
    "QualityGate",
    "QualityThresholds",
    "GateResult",
    "FidelityPolicy",
    "DEFAULT_POLICY",
    "POLICY_VERSION",
    "ReconstructionPipeline",
    "PipelineState",
    "Stage",
    "build_page_graph",
    "RepairExecutionError",
    "execute_action",
    "execute_plan",
    "audit_source_coverage",
    "extract_pptx_objects",
    "calibrate_typography",
    "measurement_loss",
    "build_text_target_spec",
    "solve_peer_layout",
    "solve_graph_relations",
    "subject_placement",
    "compare_asset_subjects",
    "EvidenceThresholds",
    "from_dual_comparison",
    "merge_difference_graphs",
    "AstraIngestionError",
    "validate_astra_object_ids",
    "ingest_astra_qa",
    "summarize_iteration",
    "convergence_delta",
    "AstraRequest",
    "build_reconstruction_request",
    "build_visual_qa_request",
    "parse_reconstruction_response",
    "parse_visual_qa_response",
]
