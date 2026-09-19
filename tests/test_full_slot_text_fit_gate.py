#!/usr/bin/env python3
"""Contract regression for the strict full-slot E3/E4 text-fit gate."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITABLE = ROOT / "ai-ppt-editable" / "scripts"
sys.path.insert(0, str(EDITABLE))

from text_fit_deck import TEXT_SLOT_KINDS  # noqa: E402


def main() -> int:
    expected = {
        "text",
        "shape_text",
        "table_cell",
        "chart_title",
        "chart_legend",
        "chart_category_label",
        "chart_data_label",
    }
    assert set(TEXT_SLOT_KINDS) == expected

    fit_source = (EDITABLE / "text_fit_deck.py").read_text(encoding="utf-8")
    for token in (
        'slide.get("texts")',
        'slide.get("shapes")',
        'slide.get("tables")',
        'slide.get("charts")',
        '"geometry_first_font_shrink_last"',
        '"all_slots_measured": True',
    ):
        assert token in fit_source, token

    compose = (EDITABLE / "compose_pptx.py").read_text(encoding="utf-8")
    gate = (EDITABLE / "text_fit_authoring_gate.py").read_text(encoding="utf-8")
    for token in (
        "from text_fit_authoring_gate import run_text_fit_e3, write_text_fit_e4_receipt",
        "run_text_fit_e3",
        'args.authoring_backend == "artifact-tool"',
        "write_text_fit_e4_receipt",
    ):
        assert token in compose, token

    # The strict Artifact Tool route must never be able to author before E3.
    e3_call = compose.index("e3_report = run_text_fit_e3")
    artifact_branch = compose.index('if args.authoring_backend == "artifact-tool":', e3_call)
    subprocess_call = compose.index("completed = subprocess.run", artifact_branch)
    assert e3_call < artifact_branch < subprocess_call

    # The extracted gate remains fail-closed; extraction must not weaken E3/E4.
    for token in (
        "from text_fit_deck import TEXT_SLOT_KINDS, audit_layout",
        'report["stage"] = "E3"',
        "target_not_fit_count",
        "geometry_defect_count",
        '"stage": "E4"',
        '"pptx_sha256"',
        '"render_validation_required": True',
        "must be paired with render/typography/visual gates",
    ):
        assert token in gate, token

    print("full-slot E3/E4 text-fit gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
