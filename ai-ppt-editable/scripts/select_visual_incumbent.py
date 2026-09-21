#!/usr/bin/env python3
"""Select a visual incumbent without turning similarity scores into release gates.

The selector is diagnostic. It accepts a challenger only when the aggregate
score improves materially and no protected region regresses beyond tolerance.
Production release remains governed by hard correctness and structured visual
closeout, never by a fixed SSIM threshold.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def score(report: dict) -> float:
    for key in ("reference_fidelity_score", "foreground_weighted_score", "whole_page_ssim", "ssim", "raw_ssim"):
        if key in report:
            return float(report[key])
    metrics = report.get("metrics")
    if isinstance(metrics, dict):
        for key in ("reference_fidelity_score", "blurred_layout_ssim", "global_ssim"):
            if key in metrics:
                return float(metrics[key])
    candidate = report.get("candidate")
    if isinstance(candidate, dict):
        for key in ("reference_fidelity_score", "whole_page_ssim", "ssim", "raw_ssim"):
            if key in candidate:
                return float(candidate[key])
    rendered = report.get("rendered_fidelity")
    if isinstance(rendered, dict) and "ssim" in rendered:
        return float(rendered["ssim"])
    raise ValueError("visual report has no supported aggregate score")


def _region_mapping(value) -> dict[str, float]:
    if isinstance(value, dict):
        output = {}
        for key, raw in value.items():
            try:
                output[str(key)] = float(raw)
            except (TypeError, ValueError):
                continue
        return output
    if isinstance(value, list):
        output = {}
        for row in value:
            if not isinstance(row, dict):
                continue
            name = row.get("region_id") or row.get("region") or row.get("id")
            raw = row.get("score")
            if name is None or raw is None:
                continue
            try:
                output[str(name)] = float(raw)
            except (TypeError, ValueError):
                continue
        return output
    return {}


def regional_scores(report: dict) -> dict[str, float]:
    candidates = [
        report.get("regional_ssim"),
        report.get("regions"),
        (report.get("candidate") or {}).get("regional_ssim") if isinstance(report.get("candidate"), dict) else None,
        (report.get("rendered_fidelity") or {}).get("regional_ssim") if isinstance(report.get("rendered_fidelity"), dict) else None,
    ]
    for value in candidates:
        output = _region_mapping(value)
        if output:
            return output
    return {}


def _repair_priority(regions: dict[str, float], limit: int) -> list[dict]:
    return [
        {"region": name, "score": round(value, 9), "rank": rank}
        for rank, (name, value) in enumerate(
            sorted(regions.items(), key=lambda item: (item[1], item[0]))[: max(1, limit)],
            start=1,
        )
    ]


def select(
    incumbent: dict,
    challenger: dict,
    *,
    strict_threshold: float | None = None,
    min_improvement: float = 0.002,
    max_region_regression: float = 0.02,
    repair_limit: int = 3,
) -> dict:
    old = score(incumbent)
    new = score(challenger)
    incumbent_regions = regional_scores(incumbent)
    challenger_regions = regional_scores(challenger)
    common = sorted(set(incumbent_regions) & set(challenger_regions))
    deltas = {name: round(challenger_regions[name] - incumbent_regions[name], 9) for name in common}
    protected = [name for name, delta in deltas.items() if delta >= 0.01]
    regressed = [name for name, delta in deltas.items() if delta <= -0.005]
    severe_regressions = [name for name, delta in deltas.items() if delta < -abs(max_region_regression)]
    aggregate_delta = round(new - old, 9)
    selected = aggregate_delta >= min_improvement and not severe_regressions
    active_regions = challenger_regions if selected else incumbent_regions
    if selected:
        status = "improved"
    elif severe_regressions:
        status = "rejected-protected-region-regression"
    else:
        status = "retained-no-material-improvement"
    return {
        "schema": "ai-ppt-plus/visual-incumbent-selection/v3",
        "valid": True,
        "selected": "challenger" if selected else "incumbent",
        "accepted_challenger": selected,
        "incumbent_score": old,
        "challenger_score": new,
        "delta": aggregate_delta,
        "minimum_material_improvement": min_improvement,
        "maximum_region_regression": max_region_regression,
        "legacy_threshold_diagnostic": strict_threshold,
        "release_ready": None,
        "status": status,
        "regional_deltas": deltas,
        "protected_regions": protected if selected else [],
        "regressed_regions": regressed,
        "severe_regressions": severe_regressions,
        "repair_priority": _repair_priority(active_regions, repair_limit),
        "policy": "scores rank repair work only; accept a materially better challenger without severe protected-region regression; release remains governed by hard correctness and structured visual closeout",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("incumbent", type=Path)
    parser.add_argument("challenger", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--strict-threshold", type=float, help="deprecated diagnostic only; never a release gate")
    parser.add_argument("--min-improvement", type=float, default=0.002)
    parser.add_argument("--max-region-regression", type=float, default=0.02)
    parser.add_argument("--repair-limit", type=int, default=3)
    args = parser.parse_args()
    result = select(
        load(args.incumbent),
        load(args.challenger),
        strict_threshold=args.strict_threshold,
        min_improvement=args.min_improvement,
        max_region_regression=args.max_region_regression,
        repair_limit=args.repair_limit,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
