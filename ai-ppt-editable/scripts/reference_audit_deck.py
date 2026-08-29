#!/usr/bin/env python3
"""Run reference preflight checks for every page in a reference directory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from atomic_output import atomic_write_json
from reference_audit import _stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_dir")
    parser.add_argument("candidate_dir")
    parser.add_argument("--expected-pages", type=int, required=True)
    parser.add_argument("--expected-ratio", type=float, default=16 / 9)
    parser.add_argument("--pages", help="only audit selected slide numbers, e.g. 1,3-4")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    selected_pages: set[int] | None = None
    if args.pages:
        selected_pages = set()
        try:
            for part in args.pages.split(","):
                token = part.strip()
                if not token:
                    raise ValueError("empty page selector")
                if "-" in token:
                    lo, hi = (int(item.strip()) for item in token.split("-", 1))
                    if lo > hi:
                        raise ValueError("page range is reversed")
                    selected_pages.update(range(lo, hi + 1))
                else:
                    selected_pages.add(int(token))
        except (TypeError, ValueError) as exc:
            result = {
                "schema": "ai-ppt-plus/reference-audit-deck/v1",
                "valid": False,
                "status": "blocked",
                "reference_dir": str(Path(args.reference_dir).resolve()),
                "candidate_dir": str(Path(args.candidate_dir).resolve()),
                "expected_pages": args.expected_pages,
                "selected_pages": [],
                "pages": [],
                "issues": [{"severity": "blocker", "code": "invalid_pages", "message": str(exc)}],
                "human_visual_review_required": True,
            }
            atomic_write_json(Path(args.report).resolve(), result)
            print(json.dumps(result, ensure_ascii=False))
            return 2
        if not selected_pages or min(selected_pages) < 1 or max(selected_pages) > args.expected_pages:
            result = {
                "schema": "ai-ppt-plus/reference-audit-deck/v1",
                "valid": False,
                "status": "blocked",
                "reference_dir": str(Path(args.reference_dir).resolve()),
                "candidate_dir": str(Path(args.candidate_dir).resolve()),
                "expected_pages": args.expected_pages,
                "selected_pages": sorted(selected_pages),
                "pages": [],
                "issues": [{"severity": "blocker", "code": "pages_out_of_range"}],
                "human_visual_review_required": True,
            }
            atomic_write_json(Path(args.report).resolve(), result)
            print(json.dumps(result, ensure_ascii=False))
            return 2

    reference_root = Path(args.reference_dir).resolve()
    candidate_root = Path(args.candidate_dir).resolve()
    pages = []
    issues = []
    audit_pages = sorted(selected_pages) if selected_pages is not None else list(range(1, args.expected_pages + 1))
    for slide_no in audit_pages:
        reference = reference_root / f"slide-{slide_no}.png"
        candidate = candidate_root / f"slide-{slide_no}.png"
        page = {"slide_no": slide_no, "reference": str(reference), "candidate": str(candidate)}
        if not reference.is_file():
            issues.append({"severity": "blocker", "code": "reference_page_missing", "slide_no": slide_no, "path": str(reference)})
            page["reference_stats"] = None
        else:
            page["reference_stats"] = _stats(reference)
            if abs(page["reference_stats"]["ratio"] - args.expected_ratio) > 0.02:
                issues.append({"severity": "blocker", "code": "reference_ratio_unexpected", "slide_no": slide_no, "ratio": page["reference_stats"]["ratio"]})
        if not candidate.is_file():
            issues.append({"severity": "blocker", "code": "candidate_page_missing", "slide_no": slide_no, "path": str(candidate)})
            page["candidate_stats"] = None
        else:
            page["candidate_stats"] = _stats(candidate)
            if abs(page["candidate_stats"]["ratio"] - args.expected_ratio) > 0.02:
                issues.append({"severity": "blocker", "code": "candidate_ratio_unexpected", "slide_no": slide_no, "ratio": page["candidate_stats"]["ratio"]})
            if page["candidate_stats"]["edge_dark_fraction"] > 0.25:
                issues.append({"severity": "blocker", "code": "candidate_may_be_letterboxed", "slide_no": slide_no})
        pages.append(page)

    result = {
        "schema": "ai-ppt-plus/reference-audit-deck/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "reference_dir": str(reference_root),
        "candidate_dir": str(candidate_root),
        "expected_pages": args.expected_pages,
        "selected_pages": audit_pages if selected_pages is not None else "all",
        "pages": pages,
        "issues": issues,
        "human_visual_review_required": True,
    }
    atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
