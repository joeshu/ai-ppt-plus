#!/usr/bin/env python3
"""Build deterministic Astra closed-loop inputs for the real 12-case replay suite.

This script does not call a model. It converts the existing replay evidence into
validated PageGraph / DifferenceGraph artifacts and provider-neutral Astra QA
requests so the host runtime can run visual reasoning without inventing a second
source of truth.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
EDITABLE = REPO / "ai-ppt-editable"
if str(EDITABLE) not in sys.path:
    sys.path.insert(0, str(EDITABLE))

from reconstruction.astra_contract import build_visual_qa_request
from reconstruction.evidence_bridge import from_dual_comparison
from reconstruction.manifest_bridge import build_page_graph


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_evidence_path(base: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return base / path


def deterministic_report(case: dict) -> dict:
    candidate = case["candidate"]
    objects = candidate.get("objects") or {}
    visual = candidate.get("visual") or {}
    errors = []
    errors.extend(objects.get("semantic_errors") or [])
    errors.extend(objects.get("case_replay_errors") or [])
    issues = []
    for picture in objects.get("whole_slide_pictures") or []:
        issues.append({
            "code": "full-slide-raster",
            "object_id": str(picture.get("object_id") if isinstance(picture, dict) else picture),
            "message": "full-slide raster detected in editable candidate",
        })
    return {
        "valid": candidate.get("technical_status") == "passed",
        "pixel_comparison": {
            "status": "passed" if visual.get("valid") else "failed",
            "metrics": dict(visual.get("metrics") or {}),
            "bindings": [{
                "reference": {"path": candidate.get("reference")},
                "rendered": {"path": candidate.get("rendered")},
            }],
        },
        "object_comparison": {
            "status": "passed" if not errors else "failed",
            "errors": errors,
            "warnings": [],
        },
        "issues": issues,
    }


def case_status(diff_graph) -> str:
    if any(item.severity == "P0" for item in diff_graph.findings):
        return "blocked-semantic"
    if diff_graph.findings:
        return "needs-astra-qa"
    return "gate-ready"


def build_case(case: dict, *, runs_root: Path, output_dir: Path) -> dict:
    case_id = case["case_id"]
    case_run = runs_root / case_id
    layout_path = case_run / "layout.json"
    manifest_path = case_run / "object-manifest.json"
    if not layout_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(f"{case_id}: missing layout/object manifest under {case_run}")

    layout = read_json(layout_path)
    manifest = read_json(manifest_path)
    page_graph = build_page_graph(layout, manifest, slide_no=1)
    report = deterministic_report(case)
    diff_graph = from_dual_comparison(report)

    candidate = case["candidate"]
    request = build_visual_qa_request(
        source_id=str(candidate.get("reference") or f"{case_id}:reference"),
        rendered_id=str(candidate.get("rendered") or f"{case_id}:rendered"),
        page_graph=asdict(page_graph),
        object_manifest=manifest,
        metric_summary=dict((candidate.get("visual") or {}).get("metrics") or {}),
    )

    case_out = output_dir / case_id
    write_json(case_out / "page-graph.json", asdict(page_graph))
    write_json(case_out / "deterministic-difference-graph.json", asdict(diff_graph))
    write_json(case_out / "astra-visual-qa-request.json", json.loads(request.to_json()))

    blocking = [item for item in diff_graph.findings if item.severity in {"P0", "P1"}]
    record = {
        "schema": "ai-ppt-plus/astra-case-convergence/v1",
        "case_id": case_id,
        "title": case.get("title"),
        "priority": case.get("priority"),
        "responsibility": case.get("responsibility"),
        "status": case_status(diff_graph),
        "iteration": 0,
        "visual_metrics": dict((candidate.get("visual") or {}).get("metrics") or {}),
        "native_editability_valid": bool((candidate.get("objects") or {}).get("native_editability_valid")),
        "semantic_audit_valid": bool((candidate.get("objects") or {}).get("semantic_audit_valid")),
        "case_replay_audit_valid": bool((candidate.get("objects") or {}).get("case_replay_audit_valid")),
        "difference_count": len(diff_graph.findings),
        "blocking_count": len(blocking),
        "domains": sorted({item.domain for item in diff_graph.findings}),
        "next_action": (
            "fix deterministic semantic blocker before Astra"
            if any(item.severity == "P0" for item in diff_graph.findings)
            else "run Astra object-local visual QA and merge DifferenceGraph"
            if diff_graph.findings
            else "evaluate QualityGate"
        ),
    }
    write_json(case_out / "convergence-record.json", record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation", type=Path, default=ROOT / "candidate-evaluation.json")
    parser.add_argument("--runs-root", type=Path, default=ROOT / "runs" / "candidate")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "astra-closed-loop")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    evaluation = read_json(args.evaluation)
    cases = evaluation.get("cases") or []
    if args.strict and len(cases) != 12:
        raise SystemExit(f"expected 12 cases, found {len(cases)}")

    records = [build_case(case, runs_root=args.runs_root, output_dir=args.output_dir) for case in cases]
    summary = {
        "schema": "ai-ppt-plus/astra-closed-loop-batch/v1",
        "suite_id": evaluation.get("suite_id"),
        "case_count": len(records),
        "status_counts": {status: sum(1 for item in records if item["status"] == status) for status in sorted({item["status"] for item in records})},
        "cases": records,
    }
    write_json(args.output_dir / "summary.json", summary)

    if args.strict:
        missing = [item["case_id"] for item in records if not item["native_editability_valid"] or not item["semantic_audit_valid"]]
        if missing:
            raise SystemExit("deterministic semantic/editability blocker: " + ", ".join(missing))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
