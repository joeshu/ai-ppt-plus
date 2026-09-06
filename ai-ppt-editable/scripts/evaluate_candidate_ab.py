#!/usr/bin/env python3
"""Evaluate a FTTR v6 candidate against an accepted v5 baseline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from reconstruction.candidate_ab import evaluate_candidate_ab


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--target-region", action="append", default=[], dest="target_regions")
    parser.add_argument("--mandatory-region", action="append", default=[], dest="mandatory_regions")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fail-on-rollback", action="store_true")
    args = parser.parse_args()

    evaluation = evaluate_candidate_ab(
        _load(args.baseline),
        _load(args.candidate),
        target_region_ids=args.target_regions,
        mandatory_region_ids=args.mandatory_regions,
    )
    _write(args.output, evaluation)
    print(json.dumps({
        "accepted": evaluation["accepted"],
        "decision": evaluation["decision"],
        "winner_variant": evaluation["winner_variant"],
        "reasons": evaluation["reasons"],
        "output": str(args.output),
    }, ensure_ascii=False))
    if args.fail_on_rollback and not evaluation["accepted"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
