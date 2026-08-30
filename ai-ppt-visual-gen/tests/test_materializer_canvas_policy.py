#!/usr/bin/env python3
"""Regression test: native-size tolerance must match the plan validator."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from materialize_visual_generation_prompts import validate_input  # noqa: E402


def main() -> int:
    plan = {
        "canvas": {"ratio": "16:9", "width_px": 2048, "height_px": 1152},
        "canvas_policy": {
            "require_exact_dimensions": False,
            "minimum_width_px": 1600,
            "minimum_height_px": 900,
            "on_mismatch": "warn",
        },
    }
    codes = [item.get("code") for item in validate_input(plan)]
    assert "canvas_exact_dimension_policy_missing" not in codes, codes
    assert "canvas_exact_dimension_policy_invalid" not in codes, codes
    assert "canvas_mismatch_policy_invalid" not in codes, codes
    print("materializer canvas tolerance: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
