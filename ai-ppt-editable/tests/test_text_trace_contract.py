#!/usr/bin/env python3
"""Regression tests for TextSpec/TextRunSpec measurement provenance."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "ai-ppt-editable" / "scripts" if (ROOT / "ai-ppt-editable" / "scripts").is_dir() else ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from text_fit_deck import _producer_kind, _text  # noqa: E402
from text_model import measurement_scope, number_unit_trace, text_trace  # noqa: E402


def main() -> int:
    spec = {
        "text_id": "metric",
        "text": "stale plain shadow",
        "runs": [
            {"run_id": "metric.number", "text": "-12.5", "style": {"font_size_pt": 20}},
            {"run_id": "metric.unit", "text": "%", "style": {"font_size_pt": 14}},
        ],
        "measurement_scope": {"kind": "sub_box", "box_id": "metric.value"},
        "number_unit": {
            "group_id": "metric",
            "number_text": "-12.5",
            "unit_text": "%",
            "number_run_id": "metric.number",
            "unit_run_id": "metric.unit",
        },
    }
    trace = text_trace(spec, fallback_id="text:metric")
    assert _text(spec) == "-12.5%"
    assert trace["text_spec_id"] == "metric"
    assert len(trace["content_sha256"]) == 64
    assert trace["content_matches_runs"] is True
    assert trace["run_ids"] == ["metric.number", "metric.unit"]
    assert trace["run_trace"][0]["style"]["font_size_pt"] == 20
    assert measurement_scope(spec, fallback_id="text:metric") == {"kind": "sub_box", "scope_id": "metric.value"}
    number_unit = number_unit_trace(spec, content=trace["content"], fallback_id="metric")
    assert number_unit["combined_text"] == "-12.5%"
    assert _producer_kind("text", spec, trace) == "number_unit"

    mismatched = dict(spec)
    mismatched["number_unit"] = dict(spec["number_unit"], unit_text="元")
    bad = text_trace(mismatched, fallback_id="text:metric")
    assert bad["content_matches_runs"] is True
    assert number_unit_trace(mismatched, content=bad["content"], fallback_id="metric")["combined_text"] == "-12.5元"
    print("text trace contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
