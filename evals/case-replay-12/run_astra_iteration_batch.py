#!/usr/bin/env python3
"""Execute repair-ready Astra cases, rollback regressions, and prepare next QA requests."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
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

ITERATION_RUNNER = ROOT / "run_astra_iteration.py"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def regression_decision(previous: dict, current: dict, *, tolerance: float = 0.0) -> dict:
    previous_score = previous.get("pixel_fidelity_score")
    current_score = current.get("pixel_fidelity_score")
    visual_delta = None
    if previous_score is not None and current_score is not None:
        visual_delta = round(float(current_score) - float(previous_score), 6)
    previous_blocking = int(previous.get("blocking_count", 0) or 0)
    current_blocking = int(current.get("blocking_count", 0) or 0)
    native_regressed = previous.get("native_editability_valid", True) is True and current.get("native_editability_valid") is not True
    visual_regressed = visual_delta is not None and visual_delta < -abs(float(tolerance))
    blocking_regressed = current_blocking > previous_blocking
    reasons = []
    if visual_regressed:
        reasons.append("pixel_fidelity_decreased")
    if blocking_regressed:
        reasons.append("blocking_count_increased")
    if native_regressed:
        reasons.append("native_editability_regressed")
    return {
        "rollback": bool(reasons),
        "reasons": reasons,
        "pixel_fidelity_delta": visual_delta,
        "blocking_delta": current_blocking - previous_blocking,
        "native_editability_regressed": native_regressed,
    }


def deterministic_report(iteration_dir: Path, reference: Path) -> dict:
    visual = read_json(iteration_dir / "visual-comparison.json")
    native = read_json(iteration_dir / "native-editability.json")
    inspect = read_json(iteration_dir / "inspect.json")
    errors = list(native.get("errors") or [])
    for issue in inspect.get("issues") or []:
        if issue.get("severity") in {"blocker", "critical"}:
            errors.append(issue)
    rendered = iteration_dir / "render" / "slide-1.png"
    return {
        "valid": not errors,
        "pixel_comparison": {
            "status": "passed" if visual.get("valid") else "failed",
            "metrics": dict(visual.get("metrics") or {}),
            "bindings": [{"reference": {"path": str(reference)}, "rendered": {"path": str(rendered)}}],
        },
        "object_comparison": {
            "status": "passed" if not errors else "failed",
            "errors": errors,
            "warnings": [],
        },
        "issues": [],
    }


def next_qa_bundle(iteration_dir: Path, reference: Path) -> dict:
    layout = read_json(iteration_dir / "layout.json")
    manifest = read_json(iteration_dir / "object-manifest.json")
    page_graph = build_page_graph(layout, manifest, slide_no=1)
    diff_graph = from_dual_comparison(deterministic_report(iteration_dir, reference))
    visual = read_json(iteration_dir / "visual-comparison.json")
    rendered = iteration_dir / "render" / "slide-1.png"
    request = build_visual_qa_request(
        source_id=str(reference),
        rendered_id=str(rendered),
        page_graph=asdict(page_graph),
        object_manifest=manifest,
        metric_summary=dict(visual.get("metrics") or {}),
    )
    return {
        "page_graph": asdict(page_graph),
        "deterministic_difference_graph": asdict(diff_graph),
        "astra_request": json.loads(request.to_json()),
        "blocking_count": len(diff_graph.blocking()),
        "difference_count": len(diff_graph.findings),
    }


def run_case(*, case_id: str, iteration: int, source_layout: Path, merged_graph: Path, reference: Path, output_dir: Path, previous_record: dict, tolerance: float) -> dict:
    case_out = output_dir / case_id / f"iteration-{iteration}"
    command = [
        sys.executable, str(ITERATION_RUNNER),
        "--case-id", case_id,
        "--layout", str(source_layout),
        "--merged-difference-graph", str(merged_graph),
        "--reference", str(reference),
        "--output-dir", str(case_out),
        "--iteration", str(iteration),
    ]
    cp = subprocess.run(command, cwd=REPO, capture_output=True, text=True, check=False)
    if cp.returncode not in {0, 2}:
        return {"case_id": case_id, "status": "execution-error", "returncode": cp.returncode, "stderr": cp.stderr[-2000:]}
    record_path = case_out / "iteration-record.json"
    if not record_path.is_file():
        return {"case_id": case_id, "status": "execution-error", "returncode": cp.returncode, "stderr": "missing iteration-record.json"}
    current = read_json(record_path)
    bundle = next_qa_bundle(case_out, reference)
    current["blocking_count"] = bundle["blocking_count"]
    current["difference_count"] = bundle["difference_count"]
    decision = regression_decision(previous_record, current, tolerance=tolerance)
    current["regression"] = decision
    if decision["rollback"]:
        rollback_dir = case_out / "rollback"
        rollback_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_layout, rollback_dir / "layout.json")
        current["status"] = "rolled-back-regression"
        current["accepted"] = False
        current["next_action"] = "retain previous accepted layout and request a different object-local repair"
    else:
        current["accepted"] = True
        current["status"] = "repaired-needs-qa"
        write_json(case_out / "page-graph.json", bundle["page_graph"])
        write_json(case_out / "deterministic-difference-graph.json", bundle["deterministic_difference_graph"])
        write_json(case_out / "astra-visual-qa-request.json", bundle["astra_request"])
        current["next_action"] = "run next Astra visual QA iteration"
    write_json(record_path, current)
    return current


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ingested-root", type=Path, required=True, help="output from ingest_astra_qa_batch.py")
    ap.add_argument("--candidate-runs", type=Path, default=ROOT / "runs" / "candidate")
    ap.add_argument("--evaluation", type=Path, default=ROOT / "candidate-evaluation.json")
    ap.add_argument("--output-root", type=Path, required=True)
    ap.add_argument("--iteration", type=int, default=1)
    ap.add_argument("--visual-regression-tolerance", type=float, default=0.0)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    evaluation = read_json(args.evaluation)
    cases_by_id = {item["case_id"]: item for item in evaluation.get("cases") or []}
    results = []
    skipped = []
    errors = []

    for case_id, case in sorted(cases_by_id.items()):
        ingested_dir = args.ingested_root / case_id / f"iteration-{args.iteration}"
        ingested_record = ingested_dir / "iteration-record.json"
        merged_graph = ingested_dir / "merged-difference-graph.json"
        if not ingested_record.is_file() or not merged_graph.is_file():
            skipped.append({"case_id": case_id, "reason": "missing-ingested-iteration"})
            continue
        previous = read_json(ingested_record)
        if previous.get("status") != "repair-ready":
            skipped.append({"case_id": case_id, "reason": previous.get("status") or "not-repair-ready"})
            continue
        source_layout = args.candidate_runs / case_id / "layout.json"
        reference_value = (case.get("candidate") or {}).get("reference")
        reference = Path(reference_value)
        if not reference.is_absolute():
            reference = ROOT / reference
        if not source_layout.is_file() or not reference.is_file():
            errors.append({"case_id": case_id, "reason": "missing-source-layout-or-reference"})
            continue
        result = run_case(
            case_id=case_id,
            iteration=args.iteration,
            source_layout=source_layout,
            merged_graph=merged_graph,
            reference=reference,
            output_dir=args.output_root,
            previous_record=previous,
            tolerance=args.visual_regression_tolerance,
        )
        results.append(result)
        if result.get("status") == "execution-error":
            errors.append(result)

    summary = {
        "schema": "ai-ppt-plus/astra-iteration-batch/v1",
        "iteration": args.iteration,
        "executed_count": len(results),
        "accepted_count": sum(1 for item in results if item.get("accepted") is True),
        "rollback_count": sum(1 for item in results if item.get("status") == "rolled-back-regression"),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "cases": results,
        "skipped": skipped,
        "errors": errors,
    }
    write_json(args.output_root / f"iteration-{args.iteration}-batch-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.strict and errors:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
