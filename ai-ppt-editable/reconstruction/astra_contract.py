#!/usr/bin/env python3
"""Provider-neutral contract for Astra visual reasoning and visual QA.

This module intentionally does not bind the repository to a specific API client.
The orchestrator passes source/render images to the host model runtime and validates
returned JSON against PageGraph/DifferenceGraph before deterministic execution.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .difference_graph import DifferenceGraph
from .graph_ir import PageGraph


RECONSTRUCTION_SYSTEM_INSTRUCTION = """You are the visual reasoning layer of a high-fidelity image-to-editable-PPTX reconstruction system.
Do not author PPTX and do not emit prose. Infer page semantics and return only PageGraph JSON.
Preserve the source image as visual ground truth. Recover native text, shape, table, chart, connector and group semantics whenever visually justified.
All bbox values MUST use normalized slide fractions [x, y, w, h], where slide top-left is (0,0) and bottom-right is (1,1). Do not emit pixels, points or inches.
Icons, illustrations and complex artistic assets must remain independent assets; do not collapse semantic content into a full-slide screenshot.
Record hierarchy, alignment, equal-size/equal-gap and connector relations when supported by visual evidence. Include confidence for uncertain inferences.
For text, preserve text content and rich-text runs when visible. Never invent hidden text or hidden data."""


VISUAL_QA_SYSTEM_INSTRUCTION = """You are the visual QA layer of a high-fidelity image-to-editable-PPTX reconstruction system.
Compare the immutable source image with the rendered candidate and the candidate object manifest.
Return only DifferenceGraph JSON. Every finding must identify an object_id and exactly one responsibility domain: geometry, typography, asset, hierarchy, or semantic.
Use hierarchy for z-order, grouping, containment, connector topology, parent/child and overlap-order mismatches. Use semantic for native object-type/data meaning mismatches.
Geometry patches MUST use the candidate PageGraph normalized fraction coordinate system. Prefer measured, bounded patches and never convert to pixels or inches.
Never request a full-page raster replacement. Semantic mismatches such as a visual table authored as an image are P0.
Use P0 for editability/semantic contract violations, P1 for major visual mismatches, P2 for visible local mismatches, P3 for polish.
Do not change correct objects merely to improve global similarity."""


@dataclass(frozen=True)
class AstraRequest:
    task: str
    system_instruction: str
    payload: dict[str, Any]

    def to_json(self) -> str:
        return json.dumps({"task": self.task, "system_instruction": self.system_instruction, "payload": self.payload}, ensure_ascii=False, indent=2)


def build_reconstruction_request(*, source_id: str, slide_width_in: float = 13.333333, slide_height_in: float = 7.5, hints: dict[str, Any] | None = None) -> AstraRequest:
    return AstraRequest(
        task="visual-reconstruction",
        system_instruction=RECONSTRUCTION_SYSTEM_INSTRUCTION,
        payload={
            "source_id": source_id,
            "target_slide": {"slide_width_in": slide_width_in, "slide_height_in": slide_height_in, "coordinate_units": "fraction"},
            "hints": hints or {},
            "output_contract": "reconstruction-graph.schema.json",
        },
    )


def build_visual_qa_request(*, source_id: str, rendered_id: str, page_graph: dict[str, Any], object_manifest: dict[str, Any], metric_summary: dict[str, Any] | None = None) -> AstraRequest:
    return AstraRequest(
        task="visual-qa",
        system_instruction=VISUAL_QA_SYSTEM_INSTRUCTION,
        payload={
            "source_id": source_id,
            "rendered_id": rendered_id,
            "page_graph": page_graph,
            "object_manifest": object_manifest,
            "metric_summary": metric_summary or {},
            "coordinate_units": "fraction",
            "output_contract": "difference-graph.schema.json",
        },
    )


def parse_reconstruction_response(data: str | dict[str, Any]) -> PageGraph:
    payload = json.loads(data) if isinstance(data, str) else data
    return PageGraph.from_dict(payload)


def parse_visual_qa_response(data: str | dict[str, Any]) -> DifferenceGraph:
    payload = json.loads(data) if isinstance(data, str) else data
    return DifferenceGraph.from_dict(payload)
