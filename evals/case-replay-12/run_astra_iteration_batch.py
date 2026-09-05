#!/usr/bin/env python3
"""Execute repair-ready Astra cases with accepted-state continuity and rollback safety."""
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

from reconstruction.accepted_state import build_accepted_state, resolve_source_layout, write_accepted_state
from reconstruction.astra_contract import build_visual_qa_request
from reconstruction.evidence_bridge import from_dual_comparison
from reconstruction.manifest_bridge import build_page_graph
from reconstruction.object_drift_guard import compare_object_drift

ITERATION_RUNNER = ROOT / "run_astra_iteration.py"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _semantic_accuracy(record: dict) -> float | None:
    value = record.get("semantic_accuracy")
    if value is None:
        value = (record.get("semantic_audit") or {}).get("accuracy")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def regression_decision(previous: dict, current: dict, *, tolerance: float = 0.0, drift_report: dict | None = None) -> dict:
    previous_score = previous.get("pixel_fidelity_score")
    if previous_score is None:
        previous_score = (previous.get("visual_metrics") or {}).get("pixel_fidelity_score")
    current_score = current.get("pixel_fidelity_score")
    visual_delta = None
    if previous_score is not None and current_score is not None:
        visual_delta = round(float(current_score) - float(previous_score), 6)
    previous_blocking = int(previous.get("blocking_count", 0) or 0)
    current_blocking = int(current.get("blocking_count", 0) or 0)
    native_regressed = previous.get("native_editability_valid", True) is True and current.get("native_editability_valid") is not True
    previous_semantic = _semantic_accuracy(previous)
    current_semantic = _semantic_accuracy(current)
    semantic_regressed = previous_semantic == 1.0 and current_semantic != 1.0
    visual_regressed = visual_delta is not None and visual_delta < -abs(float(tolerance))
    blocking_regressed = current_blocking > previous_blocking
    object_drift_regressed = drift_report is not None and drift_report.get("valid") is not True
    reasons = []
    if visual_regressed:
        reasons.append("pixel_fidelity_decreased")
    if blocking_regressed:
        reasons.append("blocking_count_increased")
    if native_regressed:
        reasons.append("native_editability_regressed")
    if semantic_regressed:
        reasons.append("semantic_accuracy_regressed")
    if object_drift_regressed:
        reasons.append("unauthorized_object_drift")
    return {
        "rollback": bool(reasons),
        "reasons": reasons,
        "pixel_fidelity_delta": visual_delta,
        "blocking_delta": current_blocking - previous_blocking,
        "native_editability_regressed": native_regressed,
        "semantic_accuracy_previous": previous_semantic,
        "semantic_accuracy_current": current_semantic,
        "semantic_accuracy_regressed": semantic_regressed,
        "unauthorized_object_drift": object_drift_regressed,
    }


def deterministic_report(iteration_dir: Path, reference: Path) -> dict:
    visual = read_json(iteration_dir / "visual-comparison.json")
    native = read_json(iteration_dir / "native-editability.json")
    semantic = read_json(iteration_dir / "semantic-audit.json")
    inspect = read_json(iteration_dir / "inspect.json")
    errors = list(native.get("errors") or []) + list(semantic.get("errors") or [])
    for issue in inspect.get("issues") or []:
        if isinstance(issue, dict) and issue.get("severity") in {"blocker", "critical"}:
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
            "warnings": list(semantic.get("warnings") or []),
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
        source_id=str(reference), rendered_id=str(rendered), page_graph=asdict(page_graph),
        object_manifest=manifest, metric_summary=dict(visual.get("metrics") or {}),
    )
    return {
        "page_graph": asdict(page_graph),
        "deterministic_difference_graph": asdict(diff_graph),
        "astra_request": json.loads(request.to_json()),
        "blocking_count": len(diff_graph.blocking()),
        "difference_count": len(diff_graph.findings),
    }


def _resolved_asset_ids(report_path: Path) -> list[str]:
    if not report_path.is_file():
        return []
    report = read_json(report_path)
    return sorted({
        str(item.get("object_id")) for item in report.get("resolved", []) or []
        if isinstance(item, dict) and item.get("object_id")
    })


def resolve_resume_layout(asset_resolved_root: Path | None, case_id: str, iteration: int) -> tuple[Path | None, dict | None]:
    if asset_resolved_root is None:
        return None, None
    for resume_path in (
        asset_resolved_root / case_id / f"iteration-{iteration}" / "resume-ready.json",
        asset_resolved_root / case_id / "resume-ready.json",
    ):
        if not resume_path.is_file():
            continue
        resume = read_json(resume_path)
        if resume.get("ready") is not True or resume.get("status") != "resume-ready":
            return None, resume
        layout_value = resume.get("layout")
        layout = Path(str(layout_value)) if layout_value else resume_path.parent / "asset-resolved-layout.json"
        if not layout.is_absolute():
            layout = resume_path.parent / layout
        if layout.is_file():
            report_path = resume_path.parent / "asset-resolution-report.json"
            return layout.resolve(), {
                **resume,
                "resolution_report": str(report_path.resolve()) if report_path.is_file() else None,
                "resolved_object_ids": _resolved_asset_ids(report_path),
            }
        return None, {**resume, "error": "resolved-layout-missing"}
    return None, None


def allowed_ids_from_execution_report(path: Path) -> set[str]:
    """Return only object IDs that the deterministic executor actually mutated.

    Model-proposed patches, deferred actions, skipped actions and regeneration requests
    are deliberately excluded. This keeps Object Drift Guard fail-closed around the
    concrete mutation set rather than trusting the model's broader proposal set.
    """
    if not path.is_file():
        return set()
    report = read_json(path)
    return {
        str(item.get("object_id")) for item in report.get("applied", []) or []
        if isinstance(item, dict) and item.get("object_id")
    }


def previous_accepted_record(case_id: str, iteration: int, output_root: Path, fallback: dict) -> dict:
    """Use the newest prior accepted record as the regression baseline when available."""
    for previous_iteration in range(iteration - 1, 0, -1):
        path = output_root / case_id / f"iteration-{previous_iteration}" / "iteration-record.json"
        if not path.is_file():
            continue
        record = read_json(path)
        if record.get("accepted") is True and not str(record.get("status") or "").startswith("rolled-back"):
            return record
    return fallback


def run_case(*, case_id: str, iteration: int, source_layout: Path, baseline_layout: Path, merged_graph: Path | None,
             reference: Path, output_dir: Path, previous_record: dict, tolerance: float,
             resume_after_assets: bool = False, allowed_object_ids: set[str] | None = None,
             source_resolution: dict | None = None) -> dict:
    case_out = output_dir / case_id / f"iteration-{iteration}"
    command = [
        sys.executable, str(ITERATION_RUNNER), "--case-id", case_id, "--layout", str(source_layout),
        "--reference", str(reference), "--output-dir", str(case_out), "--iteration", str(iteration),
    ]
    if resume_after_assets:
        command.append("--resume-after-assets")
    elif merged_graph is not None:
        command.extend(["--merged-difference-graph", str(merged_graph)])
    else:
        return {"case_id": case_id, "status": "execution-error", "stderr": "missing merged difference graph"}

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
    current["resume_after_assets"] = resume_after_assets
    current["source_resolution"] = source_resolution or {}

    if resume_after_assets:
        effective_allowed_ids = set(allowed_object_ids or set())
    else:
        effective_allowed_ids = allowed_ids_from_execution_report(case_out / "repair-execution-report.json")
    current["drift_allowed_object_ids"] = sorted(effective_allowed_ids)

    before = read_json(baseline_layout)
    after = read_json(case_out / "layout.json")
    drift_report = compare_object_drift(before, after, allowed_object_ids=effective_allowed_ids)
    write_json(case_out / "object-drift-report.json", drift_report)
    current["object_drift"] = drift_report

    decision = regression_decision(previous_record, current, tolerance=tolerance, drift_report=drift_report)
    current["regression"] = decision
    if decision["rollback"]:
        rollback_dir = case_out / "rollback"
        rollback_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(baseline_layout, rollback_dir / "layout.json")
        current["status"] = "rolled-back-regression"
        current["accepted"] = False
        current["next_action"] = "retain previous accepted layout and request a different object-local repair or regenerated asset"
    else:
        current["accepted"] = True
        current["status"] = "repaired-needs-qa"
        write_json(case_out / "page-graph.json", bundle["page_graph"])
        write_json(case_out / "deterministic-difference-graph.json", bundle["deterministic_difference_graph"])
        write_json(case_out / "astra-visual-qa-request.json", bundle["astra_request"])
        state = build_accepted_state(case_id, current, iteration_dir=case_out)
        write_accepted_state(output_dir / case_id / "accepted-state.json", state)
        current["accepted_state"] = state.to_dict()
        current["next_action"] = "run next Astra visual QA iteration from the persisted accepted state"
    write_json(record_path, current)
    return current


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ingested-root", type=Path, required=True, help="output from ingest_astra_qa_batch.py")
    ap.add_argument("--candidate-runs", type=Path, default=ROOT / "runs" / "candidate")
    ap.add_argument("--asset-resolved-root", type=Path, help="output root containing resume-ready.json from resolve_generated_assets.py")
    ap.add_argument("--evaluation", type=Path, default=ROOT / "candidate-evaluation.json")
    ap.add_argument("--output-root", type=Path, required=True)
    ap.add_argument("--iteration", type=int, default=1)
    ap.add_argument("--visual-regression-tolerance", type=float, default=0.0)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    evaluation = read_json(args.evaluation)
    cases_by_id = {item["case_id"]: item for item in evaluation.get("cases") or []}
    results, skipped, errors = [], [], []

    for case_id, case in sorted(cases_by_id.items()):
        ingested_dir = args.ingested_root / case_id / f"iteration-{args.iteration}"
        ingested_record = ingested_dir / "iteration-record.json"
        merged_graph = ingested_dir / "merged-difference-graph.json"
        if not ingested_record.is_file():
            skipped.append({"case_id": case_id, "reason": "missing-ingested-iteration"})
            continue
        ingested_previous = read_json(ingested_record)
        status = ingested_previous.get("status")
        candidate_layout = args.candidate_runs / case_id / "layout.json"
        try:
            accepted_layout, source_meta = resolve_source_layout(
                case_id=case_id, iteration=args.iteration, candidate_layout=candidate_layout, output_root=args.output_root,
            )
        except FileNotFoundError:
            errors.append({"case_id": case_id, "reason": "missing-candidate-layout"})
            continue
        regression_baseline = previous_accepted_record(case_id, args.iteration, args.output_root, ingested_previous)

        resume_layout, resume_meta = resolve_resume_layout(args.asset_resolved_root, case_id, args.iteration)
        resume_after_assets = status == "external-asset" and resume_layout is not None
        if status == "external-asset" and not resume_after_assets:
            reason = "external-asset-not-resolved"
            if resume_meta and resume_meta.get("error"):
                reason = str(resume_meta["error"])
            skipped.append({"case_id": case_id, "reason": reason})
            continue
        if status != "repair-ready" and not resume_after_assets:
            skipped.append({"case_id": case_id, "reason": status or "not-repair-ready"})
            continue

        # A resolved asset layout is the repair input, but drift and rollback are always measured
        # against the last accepted baseline, never against the original candidate after iteration 1.
        source_layout = resume_layout if resume_after_assets else accepted_layout
        baseline_layout = accepted_layout
        if not resume_after_assets and not merged_graph.is_file():
            skipped.append({"case_id": case_id, "reason": "missing-merged-difference-graph"})
            continue
        reference_value = (case.get("candidate") or {}).get("reference")
        reference = Path(reference_value)
        if not reference.is_absolute():
            reference = ROOT / reference
        if source_layout is None or not source_layout.is_file() or not baseline_layout.is_file() or not reference.is_file():
            errors.append({"case_id": case_id, "reason": "missing-source-layout-or-reference"})
            continue

        allowed_ids = set(resume_meta.get("resolved_object_ids") or []) if resume_after_assets and resume_meta else None
        result = run_case(
            case_id=case_id, iteration=args.iteration, source_layout=source_layout, baseline_layout=baseline_layout,
            merged_graph=None if resume_after_assets else merged_graph, reference=reference, output_dir=args.output_root,
            previous_record=regression_baseline, tolerance=args.visual_regression_tolerance,
            resume_after_assets=resume_after_assets, allowed_object_ids=allowed_ids, source_resolution=source_meta,
        )
        results.append(result)
        if result.get("status") == "execution-error":
            errors.append(result)

    summary = {
        "schema": "ai-ppt-plus/astra-iteration-batch/v5",
        "iteration": args.iteration,
        "executed_count": len(results),
        "asset_resumed_count": sum(1 for item in results if item.get("resume_after_assets") is True),
        "accepted_count": sum(1 for item in results if item.get("accepted") is True),
        "accepted_state_update_count": sum(1 for item in results if item.get("accepted_state")),
        "rollback_count": sum(1 for item in results if item.get("status") == "rolled-back-regression"),
        "object_drift_rollback_count": sum(1 for item in results if "unauthorized_object_drift" in ((item.get("regression") or {}).get("reasons") or [])),
        "semantic_rollback_count": sum(1 for item in results if "semantic_accuracy_regressed" in ((item.get("regression") or {}).get("reasons") or [])),
        "skipped_count": len(skipped), "error_count": len(errors), "cases": results, "skipped": skipped, "errors": errors,
    }
    write_json(args.output_root / f"iteration-{args.iteration}-batch-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 2 if args.strict and errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
