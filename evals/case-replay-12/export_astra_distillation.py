#!/usr/bin/env python3
"""Export Astra iteration evidence into distillation records and performance summary."""
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

from reconstruction.distillation_record import build_distillation_record, merge_performance_report, summarize_distillation


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _asset_report(asset_root: Path | None, case_id: str, iteration: int) -> dict:
    if asset_root is None:
        return {}
    candidates = [
        asset_root / case_id / f"iteration-{iteration}" / "asset-resolution-report.json",
        asset_root / case_id / "asset-resolution-report.json",
    ]
    for path in candidates:
        if path.is_file():
            return read_json(path)
    return {}


def collect_records(iteration_root: Path, asset_root: Path | None = None, approvals: dict | None = None) -> list[dict]:
    approvals = approvals or {}
    records = []
    for path in sorted(iteration_root.glob("*/iteration-*/iteration-record.json")):
        raw = read_json(path)
        case_id = str(raw.get("case_id") or path.parents[1].name)
        iteration = int(raw.get("iteration") or path.parent.name.split("-")[-1])
        human = approvals.get(case_id)
        if isinstance(human, dict):
            human = human.get(str(iteration), human.get("approved"))
        record = build_distillation_record(
            iteration_record=raw,
            asset_resolution=_asset_report(asset_root, case_id, iteration),
            human_approved=human if isinstance(human, bool) else None,
        ).to_dict()
        record["source_iteration_record"] = str(path)
        records.append(record)
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iteration-root", type=Path, required=True)
    ap.add_argument("--asset-root", type=Path)
    ap.add_argument("--approvals", type=Path, help="optional human approval JSON")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--performance-report", type=Path)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    approvals = read_json(args.approvals) if args.approvals and args.approvals.is_file() else {}
    records = collect_records(args.iteration_root, args.asset_root, approvals)
    summary = summarize_distillation(records)
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "records.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in records),
        encoding="utf-8",
    )
    write_json(out / "summary.json", summary)

    if args.performance_report:
        performance_path = args.performance_report.resolve()
        existing = read_json(performance_path) if performance_path.is_file() else {}
        merged = merge_performance_report(existing, summary)
        write_json(performance_path, merged)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.strict and not records:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
