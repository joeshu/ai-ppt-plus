#!/usr/bin/env python3
"""Provider-neutral contracts for Astra reconstruction, text observation and QA."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .difference_graph import DifferenceGraph
from .graph_ir import PageGraph
from .text_target_spec import build_text_target_spec


RECONSTRUCTION_SYSTEM_INSTRUCTION = """You are the visual reasoning layer of a high-fidelity image-to-editable-PPTX reconstruction system.
Do not author PPTX and do not emit prose. Infer page semantics and return only PageGraph JSON.
Preserve the source image as visual ground truth. Recover native text, shape, table, chart, connector and group semantics whenever visually justified.
All bbox values MUST use normalized slide fractions [x, y, w, h], where slide top-left is (0,0) and bottom-right is (1,1). Do not emit pixels, points or inches.
Icons, illustrations and complex artistic assets must remain independent assets; do not collapse semantic content into a full-slide screenshot.
Record hierarchy, alignment, equal-size/equal-gap and connector relations when supported by visual evidence. Include confidence for uncertain inferences.
For text, preserve text content and rich-text runs when visible. Never invent hidden text or hidden data."""

TEXT_TARGET_SYSTEM_INSTRUCTION = """You are the typography observation layer for high-fidelity screenshot-to-editable-PPTX reconstruction.
Observe the immutable source screenshot and return only JSON observations for visible text objects requested by object_id.
For each object return exact visible text, pixel bbox [x,y,w,h], one baseline y coordinate per rendered line, line_count, plausible font_candidates, estimated_font_size_pt, estimated_line_spacing, rich-text runs that exactly concatenate to the full text, and confidence.
Use separate runs when visible emphasis differs (bold, italic, color, font or size). Do not invent hidden copy, hidden styling or exact font identity when evidence is ambiguous; include multiple font candidates and reduce confidence instead.
All bbox/baseline coordinates are source-image pixels. Preserve Chinese, Latin letters, digits and punctuation exactly as visible."""

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


def build_text_target_request(*, source_id: str, object_ids: list[str], source_size_px: tuple[int, int] | list[int], hints: dict[str, Any] | None = None) -> AstraRequest:
    if not object_ids or any(not str(value).strip() for value in object_ids):
        raise ValueError("text target request requires object_ids")
    if len(source_size_px) != 2 or int(source_size_px[0]) <= 0 or int(source_size_px[1]) <= 0:
        raise ValueError("source_size_px must contain positive width/height")
    return AstraRequest(
        task="typography-target-observation",
        system_instruction=TEXT_TARGET_SYSTEM_INSTRUCTION,
        payload={
            "source_id": source_id,
            "source_size_px": [int(source_size_px[0]), int(source_size_px[1])],
            "object_ids": [str(value) for value in object_ids],
            "hints": hints or {},
            "output_contract": "text-target-observation.schema.json",
        },
    )


def parse_text_target_response(source_image: str | Path, data: str | dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(data) if isinstance(data, str) else data
    if not isinstance(payload, dict) or not isinstance(payload.get("observations"), list):
        raise ValueError("text target response requires observations[]")
    requested = payload.get("requested_object_ids")
    observations = payload["observations"]
    if requested is not None:
        requested_ids = {str(value) for value in requested}
        observed_ids = {str(item.get("object_id") or "") for item in observations if isinstance(item, dict)}
        missing = sorted(requested_ids - observed_ids)
        if missing:
            raise ValueError("text target response missing objects: " + ", ".join(missing))
    return build_text_target_spec(source_image, observations)


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
