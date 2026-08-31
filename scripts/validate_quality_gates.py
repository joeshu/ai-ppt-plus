#!/usr/bin/env python3
"""Validate the four-dimensional project quality and release gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from atomic_output import atomic_write_json

DIMENSIONS = ("content", "visual", "structure", "delivery")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("quality_gates")
    parser.add_argument("--report")
    parser.add_argument("--require-human-closeout", action="store_true")
    args = parser.parse_args()
    path = Path(args.quality_gates).resolve()
    issues = []
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result={"schema":"ai-ppt-plus/quality-gates-validation/v1","valid":False,"issues":[{"severity":"blocker","code":"quality_gates_unreadable","message":f"{type(exc).__name__}: {exc}"}]}
        if args.report: atomic_write_json(Path(args.report).resolve(),result)
        print(json.dumps(result,ensure_ascii=False)); return 3
    if not isinstance(data,dict) or data.get("schema") != "ai-ppt-plus/quality-gates/v1": issues.append({"severity":"blocker","code":"quality_gates_schema_invalid"}); data=data if isinstance(data,dict) else {}
    dimensions=data.get("dimensions") if isinstance(data.get("dimensions"),dict) else {}
    for name in DIMENSIONS:
        item=dimensions.get(name)
        if not isinstance(item,dict): issues.append({"severity":"blocker","code":"dimension_missing","dimension":name}); continue
        if item.get("status") not in {"passed","failed","pending","not-run"}: issues.append({"severity":"blocker","code":"dimension_status_invalid","dimension":name})
        if not isinstance(item.get("required"),bool): issues.append({"severity":"blocker","code":"dimension_required_invalid","dimension":name})
    technical_expected=all(dimensions.get(name,{}).get("status")=="passed" for name in DIMENSIONS if dimensions.get(name,{}).get("required",True))
    if data.get("technical_valid") is not technical_expected: issues.append({"severity":"blocker","code":"technical_status_inconsistent","expected":technical_expected,"observed":data.get("technical_valid")})
    blockers=data.get("open_blockers") or []
    if not isinstance(blockers,list): issues.append({"severity":"blocker","code":"open_blockers_invalid"}); blockers=[]
    if blockers: issues.append({"severity":"blocker","code":"open_blockers_present","count":len(blockers)})
    human=data.get("human_review_status")
    if human not in {"pending","passed","failed","not-required"}: issues.append({"severity":"blocker","code":"human_review_status_invalid"})
    # Technical evidence never supplies human closeout.  Keeping this rule
    # unconditional prevents a technically green project from being released
    # while visual/content review is still pending.
    expected_release=technical_expected and not blockers and human in {"passed","not-required"}
    if data.get("release_eligible") is not expected_release: issues.append({"severity":"blocker","code":"release_status_inconsistent","expected":expected_release,"observed":data.get("release_eligible")})
    result={"schema":"ai-ppt-plus/quality-gates-validation/v1","valid":not issues,"project_id":data.get("project_id"),"revision":data.get("revision"),"technical_valid":technical_expected,"human_review_status":human,"release_eligible":expected_release,"dimensions":{name:dimensions.get(name,{}).get("status") for name in DIMENSIONS},"issues":issues}
    if args.report: atomic_write_json(Path(args.report).resolve(),result)
    print(json.dumps(result,ensure_ascii=False)); return 0 if not issues else 2


if __name__ == "__main__": raise SystemExit(main())
