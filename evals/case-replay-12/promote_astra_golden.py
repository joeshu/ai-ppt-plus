#!/usr/bin/env python3
"""Evaluate Astra distillation history and emit versioned golden promotion manifests."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
EDITABLE = REPO / "ai-ppt-editable"
if str(EDITABLE) not in sys.path:
    sys.path.insert(0, str(EDITABLE))

from reconstruction.golden_promotion import GoldenPromotionPolicy, build_promotion_manifest, evaluate_case


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--records", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--previous-golden-root", type=Path)
    ap.add_argument("--version-prefix", default="astra-golden")
    ap.add_argument("--min-pixel-fidelity", type=float, default=0.94)
    ap.add_argument("--min-stable-iterations", type=int, default=2)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in read_jsonl(args.records.resolve()):
        case_id = str(record.get("case_id") or "")
        if case_id:
            grouped[case_id].append(record)

    policy = GoldenPromotionPolicy(
        min_pixel_fidelity_score=args.min_pixel_fidelity,
        min_consecutive_stable_iterations=max(1, args.min_stable_iterations),
    )
    out = args.output_dir.resolve()
    evaluations = []
    promoted = []
    for case_id, records in sorted(grouped.items()):
        evaluation = evaluate_case(records, policy=policy)
        evaluations.append(evaluation)
        write_json(out / case_id / "promotion-evaluation.json", evaluation)
        if not evaluation["promotable"]:
            continue
        previous = None
        if args.previous_golden_root:
            previous_path = args.previous_golden_root / case_id / "golden-manifest.json"
            if previous_path.is_file():
                previous = read_json(previous_path)
        version = f"{args.version_prefix}-{case_id}-i{evaluation['candidate_iteration']}"
        manifest = build_promotion_manifest(evaluation=evaluation, previous_golden=previous, version=version)
        write_json(out / case_id / version / "golden-manifest.json", manifest)
        write_json(out / case_id / "promotion-candidate.json", {
            "schema": "ai-ppt-plus/golden-promotion-candidate/v1",
            "case_id": case_id,
            "version": version,
            "manifest": str(out / case_id / version / "golden-manifest.json"),
            "requires_publish_step": True,
            "overwrites_existing_golden": False,
        })
        promoted.append(manifest)

    summary = {
        "schema": "ai-ppt-plus/golden-promotion-summary/v1",
        "case_count": len(grouped),
        "promotable_count": len(promoted),
        "promotable_cases": [item["case_id"] for item in promoted],
        "evaluations": evaluations,
    }
    write_json(out / "golden-promotion-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.strict and not grouped:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
