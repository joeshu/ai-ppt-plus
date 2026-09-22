#!/usr/bin/env python3
"""Build a compact, comparable performance and visual-regression ledger."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA = "ai-ppt-plus/reference-performance-ledger/v1"


def _load(path: Path | None) -> dict[str, Any]:
    if not path or not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _metric(data: dict, name: str) -> float | None:
    metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else data
    value = metrics.get(name)
    try:
        return round(float(value), 6) if value is not None else None
    except (TypeError, ValueError):
        return None


def build(*, timing: Path | None, visual: Path | None, inspection: Path | None,
          output: Path, baseline: Path | None = None, text_fit_ms: float | None = None,
          imagegen_calls: int = 0, candidate_builds: int = 1, full_renders: int = 1) -> dict:
    timing_data, visual_data, inspect_data, previous = map(_load, (timing, visual, inspection, baseline))
    slides = inspect_data.get("slides") if isinstance(inspect_data.get("slides"), list) else []
    visual_metrics = {name: _metric(visual_data, name) for name in ("global_ssim", "blurred_layout_ssim", "reference_fidelity_score")}
    previous_metrics = previous.get("visual_metrics") if isinstance(previous.get("visual_metrics"), dict) else {}
    deltas = {
        name: round(value - float(previous_metrics[name]), 6)
        for name, value in visual_metrics.items()
        if value is not None and previous_metrics.get(name) is not None
    }
    report = {
        "schema": SCHEMA,
        "status": "measured",
        "profile": timing_data.get("profile"),
        "performance": {
            "total_ms": timing_data.get("total_ms"),
            "time_to_first_visual_ms": timing_data.get("time_to_first_visual_ms") or timing_data.get("candidate_build_ms"),
            "text_fit_total_ms": text_fit_ms,
            "imagegen_call_count": max(0, imagegen_calls),
            "candidate_build_count": max(0, candidate_builds),
            "full_render_count": max(0, full_renders),
        },
        "editability": {
            "slide_count": inspect_data.get("slide_count"),
            "shape_count": sum(int(row.get("shapes", 0) or 0) for row in slides if isinstance(row, dict)),
            "text_object_count": sum(int(row.get("text_objects", 0) or 0) for row in slides if isinstance(row, dict)),
            "picture_count": sum(int(row.get("pictures", 0) or 0) for row in slides if isinstance(row, dict)),
        },
        "visual_metrics": visual_metrics,
        "baseline_comparison": {
            "available": bool(previous_metrics),
            "deltas": deltas,
            "regression_signal": any(delta < 0 for delta in deltas.values()),
            "policy": "diagnostic_only_human_visual_review_required",
        },
        "evidence": {"timing": str(timing) if timing else None, "visual": str(visual) if visual else None, "inspection": str(inspection) if inspection else None},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timing", type=Path)
    parser.add_argument("--visual", type=Path)
    parser.add_argument("--inspection", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--text-fit-ms", type=float)
    parser.add_argument("--imagegen-calls", type=int, default=0)
    parser.add_argument("--candidate-builds", type=int, default=1)
    parser.add_argument("--full-renders", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build(timing=args.timing, visual=args.visual, inspection=args.inspection, output=args.output,
                   baseline=args.baseline, text_fit_ms=args.text_fit_ms, imagegen_calls=args.imagegen_calls,
                   candidate_builds=args.candidate_builds, full_renders=args.full_renders)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
