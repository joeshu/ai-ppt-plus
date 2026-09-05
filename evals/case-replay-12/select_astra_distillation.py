#!/usr/bin/env python3
"""Select positive and hard-negative Astra distillation samples."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
EDITABLE = REPO / "ai-ppt-editable"
if str(EDITABLE) not in sys.path:
    sys.path.insert(0, str(EDITABLE))

from reconstruction.distillation_selection import DistillationSelectionPolicy, select_records


def read_records(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, items: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for item in items:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--records", type=Path, required=True, help="records.jsonl from export_astra_distillation.py")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--min-visual-delta", type=float, default=0.0)
    ap.add_argument("--allow-unapproved", action="store_true", help="do not require human approval for positive selection")
    args = ap.parse_args()

    policy = DistillationSelectionPolicy(
        min_visual_delta=args.min_visual_delta,
        require_human_approval=not args.allow_unapproved,
    )
    result = select_records(read_records(args.records), policy=policy)
    out = args.output_dir.resolve()
    write_jsonl(out / "positive-records.jsonl", result["positives"])
    write_jsonl(out / "hard-negative-records.jsonl", result["hard_negatives"])
    write_jsonl(out / "rejected-records.jsonl", result["rejected"])
    write_json(out / "selection-summary.json", {
        key: value for key, value in result.items() if key not in {"positives", "hard_negatives", "rejected"}
    })
    print(json.dumps({
        "positive_count": result["positive_count"],
        "hard_negative_count": result["hard_negative_count"],
        "rejected_count": result["rejected_count"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
