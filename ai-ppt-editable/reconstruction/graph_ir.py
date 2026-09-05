#!/usr/bin/env python3
"""Normalized intermediate representation for high-fidelity visual reconstruction.

The model layer is allowed to infer WHAT an object is and HOW objects relate.
The deterministic authoring layer consumes this module's normalized contract and
must not reinterpret model prose at render time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


ALLOWED_NODE_TYPES = {
    "text", "shape", "table", "chart", "icon", "illustration", "image",
    "connector", "group", "background", "decoration",
}
ALLOWED_RELATIONS = {
    "contains", "belongs_to", "aligned_left", "aligned_right", "aligned_top",
    "aligned_bottom", "aligned_center_x", "aligned_center_y", "equal_width",
    "equal_height", "equal_gap", "connects_to", "overlaps", "anchors_to",
}


class GraphValidationError(ValueError):
    """Raised when the visual-reconstruction IR violates a deterministic contract."""


def _bbox(value: Any) -> tuple[float, float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise GraphValidationError("bbox must contain [x, y, w, h]")
    x, y, w, h = (float(v) for v in value)
    if w < 0 or h < 0:
        raise GraphValidationError("bbox width/height must be non-negative")
    return x, y, w, h


@dataclass(frozen=True)
class Relation:
    kind: str
    target: str
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Relation":
        kind = str(data.get("kind", "")).strip()
        target = str(data.get("target", "")).strip()
        if kind not in ALLOWED_RELATIONS:
            raise GraphValidationError(f"unsupported relation kind: {kind!r}")
        if not target:
            raise GraphValidationError("relation target is required")
        confidence = float(data.get("confidence", 1.0))
        if not 0.0 <= confidence <= 1.0:
            raise GraphValidationError("relation confidence must be within [0, 1]")
        return cls(kind=kind, target=target, confidence=confidence, metadata=dict(data.get("metadata") or {}))


@dataclass(frozen=True)
class GraphNode:
    id: str
    type: str
    bbox: tuple[float, float, float, float]
    role: str | None = None
    parent_id: str | None = None
    semantic: dict[str, Any] = field(default_factory=dict)
    style: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)
    relations: tuple[Relation, ...] = field(default_factory=tuple)
    confidence: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphNode":
        node_id = str(data.get("id", "")).strip()
        node_type = str(data.get("type", "")).strip()
        if not node_id:
            raise GraphValidationError("node id is required")
        if node_type not in ALLOWED_NODE_TYPES:
            raise GraphValidationError(f"unsupported node type: {node_type!r}")
        confidence = float(data.get("confidence", 1.0))
        if not 0.0 <= confidence <= 1.0:
            raise GraphValidationError(f"node {node_id}: confidence must be within [0, 1]")
        relations = tuple(Relation.from_dict(item) for item in (data.get("relations") or []))
        return cls(
            id=node_id,
            type=node_type,
            bbox=_bbox(data.get("bbox")),
            role=data.get("role"),
            parent_id=data.get("parent_id"),
            semantic=dict(data.get("semantic") or {}),
            style=dict(data.get("style") or {}),
            source=dict(data.get("source") or {}),
            relations=relations,
            confidence=confidence,
        )


@dataclass(frozen=True)
class PageGraph:
    version: str
    slide_width: float
    slide_height: float
    reference_width: float
    reference_height: float
    nodes: tuple[GraphNode, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PageGraph":
        page = data.get("page") or {}
        graph = cls(
            version=str(data.get("version", "1.0")),
            slide_width=float(page.get("slide_width_in", 13.333333)),
            slide_height=float(page.get("slide_height_in", 7.5)),
            reference_width=float(page.get("reference_width", 0)),
            reference_height=float(page.get("reference_height", 0)),
            nodes=tuple(GraphNode.from_dict(item) for item in (data.get("nodes") or [])),
            metadata=dict(data.get("metadata") or {}),
        )
        graph.validate()
        return graph

    def validate(self) -> None:
        ids = [node.id for node in self.nodes]
        duplicates = sorted({node_id for node_id in ids if ids.count(node_id) > 1})
        if duplicates:
            raise GraphValidationError(f"duplicate node ids: {', '.join(duplicates)}")
        known = set(ids)
        for node in self.nodes:
            if node.parent_id and node.parent_id not in known:
                raise GraphValidationError(f"node {node.id}: unknown parent {node.parent_id}")
            for relation in node.relations:
                if relation.target not in known:
                    raise GraphValidationError(f"node {node.id}: unknown relation target {relation.target}")
        if self.slide_width <= 0 or self.slide_height <= 0:
            raise GraphValidationError("slide dimensions must be positive")

    def by_id(self, node_id: str) -> GraphNode:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(node_id)

    def nodes_of_type(self, *types: str) -> tuple[GraphNode, ...]:
        allowed = set(types)
        return tuple(node for node in self.nodes if node.type in allowed)

    def children_of(self, parent_id: str) -> tuple[GraphNode, ...]:
        return tuple(node for node in self.nodes if node.parent_id == parent_id)

    def editable_semantic_nodes(self) -> tuple[GraphNode, ...]:
        """Nodes that must not silently collapse into a slide-wide raster layer."""
        return self.nodes_of_type("text", "shape", "table", "chart", "connector", "group")

    def to_authoring_deck(self, *, assets_dir: str) -> dict[str, Any]:
        """Project the graph into the stable deterministic authoring backend contract.

        This intentionally performs a conservative mapping. Unsupported rich semantics
        stay in metadata for a later engine-specific expander instead of being guessed.
        """
        slide: dict[str, list[dict[str, Any]]] = {
            "texts": [], "shapes": [], "tables": [], "charts": [], "icons": [], "groups": []
        }
        for node in self.nodes:
            x, y, w, h = node.bbox
            base = {"id": node.id, "x": x, "y": y, "w": w, "h": h, "graph_metadata": node.semantic}
            if node.type == "text":
                item = dict(base)
                item.update(node.style)
                item["text"] = node.semantic.get("text", "")
                if "runs" in node.semantic:
                    item["runs"] = node.semantic["runs"]
                slide["texts"].append(item)
            elif node.type == "shape":
                item = dict(base)
                item.update(node.style)
                slide["shapes"].append(item)
            elif node.type == "table":
                item = dict(base)
                item.update(node.semantic)
                item["native_required"] = True
                slide["tables"].append(item)
            elif node.type == "chart":
                item = dict(base)
                item.update(node.semantic)
                item["native_required"] = True
                slide["charts"].append(item)
            elif node.type == "icon":
                item = dict(base)
                item.update(node.source)
                slide["icons"].append(item)
            elif node.type == "group":
                item = dict(base)
                item["children"] = [child.id for child in self.children_of(node.id)]
                slide["groups"].append(item)
        return {
            "assets_dir": assets_dir,
            "slide_width_in": self.slide_width,
            "slide_height_in": self.slide_height,
            "ref_width": self.reference_width,
            "ref_height": self.reference_height,
            "require_native_structure": True,
            "slides": [slide],
            "reconstruction_graph_version": self.version,
        }
