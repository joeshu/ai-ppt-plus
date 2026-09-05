#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    case_path = ROOT / "evals" / "unicom-next-work-card-01.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    assert case["route"] == "reference-reconstruction"
    assert case["visual_inventory_authority"] == "page-graph.json"
    gates = case["required_gates"]
    assert gates["page_graph_required"] is True
    assert gates["page_graph_drives_imagegen_requirement"] is True
    assert gates["object_manifest_crosscheck_required"] is True
    assert gates["imagegen_asset_coverage_required"] is True
    assert gates["native_imagegen_for_non_brand_icons"] is True
    assert gates["generic_icon_substitution_forbidden"] is True
    assert gates["source_crop_icon_requires_explicit_user_fallback"] is True
    assert gates["brand_logo_source_exception"] is True
    assert gates["no_visual_asset_nodes_means_no_imagegen_requirement"] is True
    assert gates["cjk_embedded_font_required"] is True
    assert gates["typography_calibration_required"] is True
    assert gates["title_single_line_guard"] is True
    assert gates["richtext_emphasis_same_text_object"] is True
    required_codes = {
        "reference_page_graph_missing",
        "visual_asset_inventory_mismatch",
        "imagegen_final_asset_manifest_missing",
        "imagegen_final_asset_gate_failed",
        "imagegen_asset_coverage_missing",
        "final_asset_route_requires_native_imagegen",
        "reference_cjk_requires_embedded_fonts",
        "reference_cjk_font_evidence_missing",
    }
    assert required_codes.issubset(set(case["blocking_codes"]))
    print("unicom next-work regression contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
