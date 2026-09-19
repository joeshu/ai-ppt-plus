#!/usr/bin/env python3
"""Regression gate for native chart missing values.

A visually missing data point must remain a gap all the way into the strict
Artifact Tool authoring contract.  It must never be normalized to numeric zero,
which would draw a false line to the chart baseline.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORING = ROOT / "ai-ppt-editable" / "scripts" / "artifact_tool_authoring.mjs"


def main() -> int:
    source = AUTHORING.read_text(encoding="utf-8")

    assert "display_blanks_as" in source and "displayBlanksAs" in source, (
        "strict authoring must forward the explicit blank rendering policy"
    )
    assert "displayBlanksAs:" in source, (
        "native chart config must carry displayBlanksAs to Artifact Tool"
    )

    # Guard against the common regression that silently turns missing values
    # into zero before authoring.  Missing points must remain null/blank.
    forbidden = (
        "value ?? 0",
        "value || 0",
        "Number(value || 0)",
        "Number(value ?? 0)",
    )
    chart_start = source.index("function addChart")
    chart_end = source.index("async function main", chart_start)
    chart_source = source[chart_start:chart_end]
    assert not any(token in chart_source for token in forbidden), (
        "chart authoring must not zero-fill missing series values"
    )

    reconstruction = (ROOT / "tests" / "test_chart_reconstruction.py").read_text(encoding="utf-8")
    assert '"missing_value_policy": "blank_not_zero"' in reconstruction
    assert "missing_value_policy_invalid" in reconstruction

    print("native chart blank-gap contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
