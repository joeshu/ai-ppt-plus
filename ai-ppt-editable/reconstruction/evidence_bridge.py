#!/usr/bin/env python3
"""Convert deterministic comparison evidence into DifferenceGraph findings.

This bridge deliberately does not invent object-level repair parameters from a
page-level pixel score.  Deterministic evidence identifies blockers and the
responsibility domain; Astra visual QA can then add object-local diagnosis and
bounded patches.  Deterministic P0/P1 findings are never discarded by merging.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .difference_graph import DifferenceFinding, DifferenceGraph


@dataclass(frozen=True)
class EvidenceThresholds:
    layout_ssim_p1: float = 0.90
    layout_ssim_p2: float = 0.96
    pixel_fidelity_p1: float = 0.82
    pixel_fidelity_p2: float = 0.92


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _severity_for_visual(metrics: dict[str, Any], thresholds: EvidenceThresholds) -> str | None:
    ssim = _float(metrics.get("blurred_layout_ssim"))
    fidelity = _float(metrics.get("pixel_fidelity_score"))
    if (ssim is not None and ssim < thresholds.layout_ssim_p1) or (fidelity is not None and fidelity < thresholds.pixel_fidelity_p1):
        return "P1"
    if (ssim is not None and ssim < thresholds.layout_ssim_p2) or (fidelity is not None and fidelity < thresholds.pixel_fidelity_p2):
        return "P2"
    return None


def _record_message(record: Any) -> tuple[str, str | None, str | None]:
    if isinstance(record, dict):
        code = str(record.get("code") or record.get("kind") or "object-audit")
        object_id = record.get("object_id") or record.get("id") or record.get("expected_object_id")
        message = record.get("message") or record.get("detail") or record.get("error") or code
        return str(message), str(object_id) if object_id else None, code
    return str(record), None, None


def _semantic_patch(record: Any) -> dict[str, Any]:
    """Return a patch only when audit evidence explicitly supplies safe intent."""
    if not isinstance(record, dict):
        return {}
    patch: dict[str, Any] = {}
    expected_type = record.get("expected_type") or record.get("target_type")
    if expected_type in {"text", "shape", "table", "chart", "icon", "group"}:
        patch["target_type"] = expected_type
    if record.get("native_required") is not None:
        patch["native_required"] = bool(record["native_required"])
    return patch


def from_dual_comparison(report: dict[str, Any], *, thresholds: EvidenceThresholds | None = None) -> DifferenceGraph:
    """Create deterministic findings from compare_dual.py output."""
    thresholds = thresholds or EvidenceThresholds()
    findings: list[dict[str, Any]] = []
    pixel = report.get("pixel_comparison") if isinstance(report.get("pixel_comparison"), dict) else {}
    pages = pixel.get("page_metrics") if isinstance(pixel.get("page_metrics"), list) else []
    if pages:
        for index, page in enumerate(pages, 1):
            if not isinstance(page, dict):
                continue
            slide = page.get("slide", index)
            metrics = page.get("metrics") if isinstance(page.get("metrics"), dict) else {}
            severity = _severity_for_visual(metrics, thresholds)
            if severity:
                findings.append({
                    "id": f"det:visual:slide-{slide}",
                    "object_id": f"slide:{slide}:visual",
                    "domain": "geometry",
                    "severity": severity,
                    "message": "deterministic render comparison is below visual-fidelity threshold; object-local diagnosis required",
                    "confidence": 1.0,
                    "metrics": metrics,
                    "proposed_patch": {},
                    "evidence": {"source": "dual-comparison", "kind": "pixel", "slide": slide},
                })
    else:
        metrics = pixel.get("metrics") if isinstance(pixel.get("metrics"), dict) else {}
        if not metrics:
            aggregate = pixel.get("aggregate") if isinstance(pixel.get("aggregate"), dict) else {}
            metrics = {
                "blurred_layout_ssim": aggregate.get("worst_blurred_layout_ssim"),
                "pixel_fidelity_score": aggregate.get("mean_pixel_fidelity_score"),
            }
        severity = _severity_for_visual(metrics, thresholds)
        if severity:
            findings.append({
                "id": "det:visual:slide-1",
                "object_id": "slide:1:visual",
                "domain": "geometry",
                "severity": severity,
                "message": "deterministic render comparison is below visual-fidelity threshold; object-local diagnosis required",
                "confidence": 1.0,
                "metrics": metrics,
                "proposed_patch": {},
                "evidence": {"source": "dual-comparison", "kind": "pixel", "slide": 1},
            })

    obj = report.get("object_comparison") if isinstance(report.get("object_comparison"), dict) else {}
    records: list[tuple[Any, str]] = []
    for item in obj.get("errors", []) or []:
        records.append((item, "P0"))
    for item in obj.get("warnings", []) or []:
        records.append((item, "P2"))
    for index, (record, severity) in enumerate(records, 1):
        message, object_id, code = _record_message(record)
        findings.append({
            "id": f"det:semantic:{index}:{code or 'audit'}",
            "object_id": object_id or f"slide:unknown:semantic-{index}",
            "domain": "semantic",
            "severity": severity,
            "message": message,
            "confidence": 1.0,
            "metrics": {},
            "proposed_patch": _semantic_patch(record),
            "evidence": {"source": "dual-comparison", "kind": "object-audit", "record": record},
        })

    for issue_index, issue in enumerate(report.get("issues", []) or [], 1):
        message, object_id, code = _record_message(issue)
        findings.append({
            "id": f"det:contract:{issue_index}:{code or 'issue'}",
            "object_id": object_id or f"comparison:contract:{issue_index}",
            "domain": "semantic",
            "severity": "P0",
            "message": message,
            "confidence": 1.0,
            "proposed_patch": {},
            "evidence": {"source": "dual-comparison", "kind": "contract", "record": issue},
        })

    bindings = pixel.get("bindings") if isinstance(pixel.get("bindings"), list) else []
    source_id = "reference"
    rendered_id = "rendered"
    if bindings and isinstance(bindings[0], dict):
        source_id = str((bindings[0].get("reference") or {}).get("path") or source_id)
        rendered_id = str((bindings[0].get("rendered") or {}).get("path") or rendered_id)
    return DifferenceGraph.from_dict({
        "version": "1.0",
        "source_id": source_id,
        "rendered_id": rendered_id,
        "findings": findings,
        "aggregate": {
            "dual_comparison_valid": report.get("valid") is True,
            "pixel_status": pixel.get("status"),
            "object_status": obj.get("status"),
        },
        "metadata": {"evidence_source": "ai-ppt-plus/dual-comparison/v1"},
    })


_SEVERITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def merge_difference_graphs(deterministic: DifferenceGraph, *additional: DifferenceGraph) -> DifferenceGraph:
    """Merge deterministic and Astra findings without allowing model evidence to erase blockers."""
    findings: list[DifferenceFinding] = list(deterministic.findings)
    seen_ids = {item.id for item in findings}
    deterministic_keys = {(item.object_id, item.domain, item.message) for item in findings}
    for graph in additional:
        for item in graph.findings:
            key = (item.object_id, item.domain, item.message)
            if key in deterministic_keys:
                continue
            candidate_id = item.id
            suffix = 2
            while candidate_id in seen_ids:
                candidate_id = f"{item.id}:{suffix}"
                suffix += 1
            if candidate_id != item.id:
                item = DifferenceFinding(
                    id=candidate_id,
                    object_id=item.object_id,
                    domain=item.domain,
                    severity=item.severity,
                    message=item.message,
                    confidence=item.confidence,
                    metrics=item.metrics,
                    proposed_patch=item.proposed_patch,
                    evidence=item.evidence,
                )
            findings.append(item)
            seen_ids.add(candidate_id)
    findings.sort(key=lambda item: (_SEVERITY_RANK[item.severity], item.domain, item.object_id, item.id))
    return DifferenceGraph(
        version=deterministic.version,
        source_id=deterministic.source_id,
        rendered_id=deterministic.rendered_id,
        findings=tuple(findings),
        aggregate={**deterministic.aggregate, "merged_graph_count": 1 + len(additional)},
        metadata={**deterministic.metadata, "merged_with_astra": bool(additional)},
    )
