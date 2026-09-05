#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    case_path = ROOT / "evals" / "unicom-next-work-card-01.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    assert case["route"] == "reference-reconstruction"
    gates = case["required_gates"]
    assert gates["native_imagegen_for_non_brand_icons"] is True
    assert gates["generic_icon_substitution_forbidden"] is True
    assert gates["source_crop_icon_requires_explicit_user_fallback"] is True
    assert gates["brand_logo_source_exception"] is True
    assert gates["cjk_embedded_font_required"] is True
    assert gates["typography_calibration_required"] is True
    assert gates["title_single_line_guard"] is True
    assert gates["richtext_emphasis_same_text_object"] is True
    required_codes = {
        "final_asset_route_requires_native_imagegen",
        "imagegen_final_asset_manifest_missing",
        "imagegen_final_asset_gate_failed",
        "reference_cjk_requires_embedded_fonts",
        "reference_cjk_font_evidence_missing",
    }
    assert required_codes.issubset(set(case["blocking_codes"]))
    print("unicom next-work regression contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
