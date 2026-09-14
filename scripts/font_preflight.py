#!/usr/bin/env python3
"""Fail-closed validation for font discovery and native render evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from atomic_output import atomic_write_json


REQUIRED_WEIGHTS = (400, 500, 600, 700)


def validate_font_evidence(report: Mapping[str, Any], *, require_cjk: bool = True, require_native_render: bool = True) -> dict[str, Any]:
    """Normalize a probe report and return explicit issues.

    A family declaration or a successful font file scan cannot set the native
    render flag.  Only an actual smoke-render report with the same family and
    font SHA list may set ``native_font_rendering_verified`` to true.
    """
    issues: list[dict[str, Any]] = []
    font_status = report.get("font_status") if isinstance(report.get("font_status"), Mapping) else {}
    cjk_ready = report.get("cjk_delivery_supported") is True
    if require_cjk and not cjk_ready:
        issues.append({"severity": "blocker", "code": "cjk_font_unresolved"})
    weights = sorted({int(value) for value in (report.get("weights_found") or []) if isinstance(value, int) and value > 0})
    missing = [weight for weight in REQUIRED_WEIGHTS if weight not in weights]
    declared_missing = sorted({int(value) for value in (report.get("missing_weights") or []) if isinstance(value, int)})
    if declared_missing != missing:
        issues.append({"severity": "blocker", "code": "font_weight_evidence_mismatch", "expected": missing, "observed": declared_missing})
    if report.get("fallback") is True or font_status.get("silent_fallback") is True:
        issues.append({"severity": "blocker", "code": "font_fallback_detected"})
    native_verified = report.get("native_font_rendering_verified") is True
    if require_native_render and not native_verified:
        issues.append({"severity": "blocker", "code": "native_font_rendering_unverified"})
    return {
        "schema": "ai-ppt-plus/font-preflight/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "cjk_ready": cjk_ready,
        "weights_found": weights,
        "missing_weights": missing,
        "simulated_bold_possible": 700 not in weights,
        "native_font_rendering_verified": native_verified,
        "fallback": bool(report.get("fallback") or font_status.get("silent_fallback")),
        "issues": issues,
    }


def smoke_texts() -> list[str]:
    """Canonical smoke strings used by every renderer adapter."""
    return ["中文标题", "中文正文与 English 123", "标点：，。！？（）", "Regular / Medium / Bold", "红色强调 蓝色强调"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="probe_fonts.py JSON report")
    parser.add_argument("--output", "-o", required=True)
    parser.add_argument("--require-cjk", action="store_true")
    parser.add_argument("--require-native-render", action="store_true")
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    result = validate_font_evidence(report, require_cjk=args.require_cjk, require_native_render=args.require_native_render)
    atomic_write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
