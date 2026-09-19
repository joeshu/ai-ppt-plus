#!/usr/bin/env python3
"""E3/E4 strict text, chart and reference-asset gates shared by authoring entrypoints."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from text_fit_deck import TEXT_SLOT_KINDS, audit_layout
from validate_brand_asset_coverage import validate_brand_coverage
from validate_chart_authoring_contract import validate_chart_authoring_contract
from validate_text_topology import audit_text_topology
from validate_page_geometry import audit_page_geometry
from validate_measured_line_boxes import audit_measured_line_boxes


def run_text_fit_e3(deck: dict, layout_path: Path, report_path: Path, *, required: bool) -> dict:
    """Measure text and fail closed on declared reference topology, brand and chart contracts."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".text-fit-e3-", dir=str(report_path.parent)) as raw:
        normalized = Path(raw) / "normalized-layout.json"
        normalized.write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = audit_layout(normalized)
        topology = audit_text_topology(normalized)
    brand = validate_brand_coverage(layout_path.resolve().parent)
    chart = validate_chart_authoring_contract(layout_path.resolve(), deck)
    page_geometry = audit_page_geometry(layout_path.resolve(), deck)
    line_boxes = audit_measured_line_boxes(layout_path.resolve(), deck)
    report["stage"] = "E3"
    report["source_layout"] = str(layout_path.resolve())
    report["required_slot_kinds"] = list(TEXT_SLOT_KINDS)
    report["blocking"] = bool(required)
    report["text_topology"] = topology
    report["topology_defect_count"] = len(topology.get("issues") or [])
    report["brand_asset_coverage"] = brand
    report["brand_defect_count"] = len(brand.get("issues") or [])
    report["chart_authoring_contract"] = chart
    report["chart_defect_count"] = len(chart.get("issues") or [])
    report["page_geometry"] = page_geometry
    report["page_geometry_defect_count"] = len(page_geometry.get("issues") or [])
    report["measured_line_boxes"] = line_boxes
    report["measured_line_box_defect_count"] = len(line_boxes.get("issues") or [])
    report["gate_passed"] = bool(
        report.get("valid")
        and report.get("all_slots_measured")
        and int(report.get("target_not_fit_count") or 0) == 0
        and int(report.get("geometry_defect_count") or 0) == 0
        and topology.get("valid")
        and brand.get("valid")
        and chart.get("valid")
        and page_geometry.get("valid")
        and line_boxes.get("valid")
    )
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def text_fit_failure_message(report: dict) -> str:
    return (
        "E3 strict authoring gate failed: "
        f"target_not_fit={report.get('target_not_fit_count')}, "
        f"geometry_defects={report.get('geometry_defect_count')}, "
        f"topology_defects={report.get('topology_defect_count')}, "
        f"brand_defects={report.get('brand_defect_count')}, "
        f"chart_defects={report.get('chart_defect_count')}, "
        f"page_geometry_defects={report.get('page_geometry_defect_count')}, "
        f"measured_line_box_defects={report.get('measured_line_box_defect_count')}, "
        f"duplicates={len(report.get('duplicate_object_ids') or [])}; "
        "repair geometry/reference line topology/brand/chart representation before composition"
    )


def write_text_fit_e4_receipt(report_path: Path, output_path: Path, e3: dict, *, required: bool) -> dict | None:
    """Bind successful E3 evidence to the exact authored PPTX for E4 QA."""
    if not output_path.is_file():
        return None
    payload = {
        "schema": "ai-ppt-plus/text-fit-e4-receipt/v2",
        "stage": "E4",
        "valid": bool(e3.get("gate_passed")),
        "blocking": bool(required),
        "pptx": str(output_path),
        "pptx_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "e3_schema": e3.get("schema"),
        "slot_count": e3.get("slot_count"),
        "coverage_by_kind": e3.get("coverage_by_kind", {}),
        "target_not_fit_count": e3.get("target_not_fit_count"),
        "geometry_defect_count": e3.get("geometry_defect_count"),
        "topology_defect_count": e3.get("topology_defect_count"),
        "brand_defect_count": e3.get("brand_defect_count"),
        "chart_defect_count": e3.get("chart_defect_count"),
        "page_geometry_defect_count": e3.get("page_geometry_defect_count"),
        "measured_line_box_defect_count": e3.get("measured_line_box_defect_count"),
        "render_validation_required": True,
        "strict_reference_release_required": True,
        "release_note": "E4 receipt is not a visual pass. Fixed-reference work must run strict_reference_release.py and pass its fresh rendered reference gate.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
