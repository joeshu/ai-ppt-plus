#!/usr/bin/env python3
"""E3/E4 full-slot text-fit gates shared by PPTX authoring entrypoints."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from text_fit_deck import TEXT_SLOT_KINDS, audit_layout


def run_text_fit_e3(deck: dict, layout_path: Path, report_path: Path, *, required: bool) -> dict:
    """Measure every formal text-producing slot before authoring."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".text-fit-e3-", dir=str(report_path.parent)) as raw:
        normalized = Path(raw) / "normalized-layout.json"
        normalized.write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = audit_layout(normalized)
    report["stage"] = "E3"
    report["source_layout"] = str(layout_path.resolve())
    report["required_slot_kinds"] = list(TEXT_SLOT_KINDS)
    report["blocking"] = bool(required)
    report["gate_passed"] = bool(
        report.get("valid")
        and report.get("all_slots_measured")
        and int(report.get("target_not_fit_count") or 0) == 0
        and int(report.get("geometry_defect_count") or 0) == 0
    )
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def text_fit_failure_message(report: dict) -> str:
    return (
        "E3 full-slot text-fit gate failed: "
        f"target_not_fit={report.get('target_not_fit_count')}, "
        f"geometry_defects={report.get('geometry_defect_count')}, "
        f"duplicates={len(report.get('duplicate_object_ids') or [])}; "
        "repair geometry first and shrink font only as a last resort"
    )


def write_text_fit_e4_receipt(report_path: Path, output_path: Path, e3: dict, *, required: bool) -> dict | None:
    """Bind the successful E3 audit to the exact authored PPTX for E4 QA."""
    if not output_path.is_file():
        return None
    payload = {
        "schema": "ai-ppt-plus/text-fit-e4-receipt/v1",
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
        "render_validation_required": True,
        "release_note": "E4 receipt must be paired with render/typography/visual gates; it is not a visual-pass substitute.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
