#!/usr/bin/env python3
"""Create a small user-facing acceptance summary from full run evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from atomic_output import atomic_write_json


def compact(report: dict) -> dict:
    profile = str(report.get("execution_profile") or "fast").lower()
    phases = report.get("phases") if isinstance(report.get("phases"), dict) else {}
    incomplete = [name for name, value in phases.items() if not (
        value is True or isinstance(value, dict) and value.get("status") in
        {"done", "passed", "complete", "completed"}
    )]
    performance = report.get("performance") if isinstance(report.get("performance"), dict) else {}
    quality = report.get("quality_evidence") if isinstance(report.get("quality_evidence"), dict) else {}
    performance_evidence = quality.get("performance") if isinstance(quality.get("performance"), dict) else {}
    if not performance and isinstance(performance_evidence.get("execution"), dict):
        performance = performance_evidence["execution"]
    benchmark = report.get("benchmark") if isinstance(report.get("benchmark"), dict) else {}
    final = report.get("final") if isinstance(report.get("final"), dict) else {}
    pages = report.get("pages") if isinstance(report.get("pages"), list) else []
    crop_count = sum(len(page.get("local_crops") or []) for page in pages if isinstance(page, dict))
    pipeline_mode = isinstance(report.get("steps"), list) or "technical_valid" in report
    if pipeline_mode:
        incomplete = [
            str(step.get("name") or step.get("step") or "unknown")
            for step in report.get("steps") or []
            if isinstance(step, dict) and not (
                step.get("ok") is True or step.get("status") in {"passed", "done", "cached"}
            )
        ]
    render = report.get("render_evidence") if isinstance(report.get("render_evidence"), dict) else {}
    if not render and isinstance(report.get("render_report"), dict):
        render = report["render_report"]
    authoritative = render.get("authoritative_visual_evidence")
    acceptance = render.get("visual_acceptance_status")
    blocked = bool(report.get("hard_blockers")) or bool(incomplete)
    if pipeline_mode:
        blocked = blocked or report.get("technical_valid") is not True
    return {
        "schema": "ai-ppt-plus/compact-acceptance/v1",
        "execution_profile": profile,
        "status": "blocked" if blocked else "passed",
        "incomplete_phases": incomplete,
        "hard_blockers": report.get("hard_blockers") or [],
        "exceptions": report.get("exceptions") or [],
        "high_risk_text": report.get("high_risk_text") or [],
        "evidence": {
            "candidate_build_count": performance.get("candidate_build_count"),
            "full_render_count": performance.get("full_render_count"),
            "local_crop_count": crop_count,
            "imagegen_call_count": benchmark.get("imagegen_call_count"),
            "native_text_coverage": benchmark.get("native_text_coverage"),
            "material_mismatch_count": benchmark.get("material_mismatch_count"),
            "authoritative_visual_renderer": performance.get("authoritative_visual_renderer"),
            "text_fit_total_ms": performance.get("text_fit_total_ms"),
            "render_attempt_count": performance.get("render_attempt_count"),
            "visual_regression_status": performance.get("visual_regression_status"),
            "renderer": render.get("renderer") or performance.get("authoritative_visual_renderer"),
            "renderer_role": render.get("renderer_role"),
            "authoritative_visual_evidence": authoritative,
            "visual_acceptance_status": acceptance,
        },
        "deliverable": {
            "pptx_path": final.get("pptx_path"),
            "pptx_sha256": final.get("pptx_sha256"),
            "render_path": final.get("render_path"),
            "render_sha256": final.get("render_sha256"),
        },
        "full_report_retained": True,
        "source_report_kind": "pipeline-result" if pipeline_mode else "short-loop-run",
        "final_visual_signoff_eligible": authoritative is True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compact(json.loads(args.report.read_text(encoding="utf-8")))
    atomic_write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
