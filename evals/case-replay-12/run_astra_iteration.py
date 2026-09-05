#!/usr/bin/env python3
"""Execute one validated Astra repair iteration through the deterministic PPTX engine.

This runner never edits PPTX XML directly. It applies a validated merged
DifferenceGraph to layout.json, then reuses compose/render/manifest/native-audit/
semantic-audit/visual-compare entrypoints to produce the next iteration evidence.

When --resume-after-assets is used, the supplied layout is already asset-resolved
and validated. In that mode the runner intentionally skips the original repair
plan so regenerate findings are not dispatched a second time; it only rebuilds,
renders and re-audits the resolved deck.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
EDITABLE = REPO / "ai-ppt-editable"
SCRIPTS = EDITABLE / "scripts"
if str(EDITABLE) not in sys.path:
    sys.path.insert(0, str(EDITABLE))

from reconstruction.difference_graph import DifferenceGraph
from reconstruction.repair_executors import execute_plan
from reconstruction.repair_router import RepairRouter


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(command: list[str], *, allow: set[int] = {0}) -> subprocess.CompletedProcess:
    cp = subprocess.run(command, cwd=REPO, capture_output=True, text=True, check=False)
    if cp.returncode not in allow:
        raise RuntimeError(
            f"command failed ({cp.returncode}): {' '.join(command)}\nSTDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}"
        )
    return cp


def prepare_repaired_layout(layout: dict, merged_graph: dict) -> dict:
    graph = DifferenceGraph.from_dict(merged_graph)
    plan = RepairRouter().build_plan(graph)
    if plan.has_blocking_deferred:
        raise RuntimeError("repair plan has blocking deferred findings")
    executed = execute_plan(layout, plan)
    if executed["report"]["requires_external_asset_generation"]:
        raise RuntimeError("repair plan requires external asset generation before deterministic iteration")
    if not executed["report"]["applied"]:
        raise RuntimeError("repair plan has no executable deterministic actions")
    return executed


def prepare_asset_resolved_layout(layout: dict) -> dict:
    return {
        "deck": deepcopy(layout),
        "report": {
            "applied": [],
            "skipped": [],
            "regeneration_requests": [],
            "deferred": [],
            "valid": True,
            "requires_external_asset_generation": False,
            "asset_resolution_resume": True,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--layout", type=Path, required=True)
    ap.add_argument("--merged-difference-graph", type=Path)
    ap.add_argument("--reference", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--iteration", type=int, required=True)
    ap.add_argument("--resume-after-assets", action="store_true")
    ap.add_argument("--font-dir", type=Path, default=EDITABLE / "assets" / "fonts")
    args = ap.parse_args()

    if not args.resume_after_assets and args.merged_difference_graph is None:
        ap.error("--merged-difference-graph is required unless --resume-after-assets is used")

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    layout = read_json(args.layout.resolve())
    if args.resume_after_assets:
        executed = prepare_asset_resolved_layout(layout)
    else:
        merged = read_json(args.merged_difference_graph.resolve())
        executed = prepare_repaired_layout(layout, merged)

    repaired_layout = out / "layout.json"
    write_json(repaired_layout, executed["deck"])
    write_json(out / "repair-execution-report.json", executed["report"])

    pptx = out / "editable.pptx"
    render_dir = out / "render"
    render_report = out / "render-report.json"
    object_manifest = out / "object-manifest.json"
    native_report = out / "native-editability.json"
    semantic_report = out / "semantic-audit.json"
    inspect_report = out / "inspect.json"
    visual_report = out / "visual-comparison.json"

    run([
        sys.executable, str(SCRIPTS / "compose_pptx.py"), str(repaired_layout), str(pptx),
        "--strict-input", "--require-native-structure",
    ])
    run([
        sys.executable, str(SCRIPTS / "render_pptx.py"), str(pptx),
        "--output-dir", str(render_dir), "--font-dir", str(args.font_dir), "--report", str(render_report),
    ])
    run([sys.executable, str(SCRIPTS / "inspect_pptx.py"), str(pptx), "--report", str(inspect_report)], allow={0, 2})
    run([
        sys.executable, str(SCRIPTS / "build_object_manifest.py"), str(repaired_layout),
        "--output", str(object_manifest),
    ])
    run([
        sys.executable, str(SCRIPTS / "validate_native_editability.py"), str(pptx),
        "--object-manifest", str(object_manifest), "--require-native-structure",
        "--require-complete-manifest", "--report", str(native_report),
    ], allow={0, 2})
    run([
        sys.executable, str(SCRIPTS / "semantic_object_audit.py"), str(pptx),
        "--object-manifest", str(object_manifest), "--report", str(semantic_report),
    ], allow={0, 2})

    rendered = render_dir / "slide-1.png"
    if not rendered.is_file():
        raise RuntimeError("iteration render did not produce slide-1.png")
    run([
        sys.executable, str(SCRIPTS / "compare_visual.py"), str(rendered), str(args.reference.resolve()),
        "--raw-slide", "--report", str(visual_report),
    ], allow={0, 2})

    visual = read_json(visual_report)
    native = read_json(native_report)
    semantic = read_json(semantic_report)
    inspect = read_json(inspect_report)
    metrics = dict(visual.get("metrics") or {})
    semantic_valid = semantic.get("valid") is True
    semantic_accuracy = 1.0 if semantic_valid else 0.0
    native_valid = native.get("valid") is True
    status = "repaired-needs-qa"
    if not native_valid:
        status = "blocked-native-regression"
    elif not semantic_valid:
        status = "blocked-semantic-regression"
    record = {
        "schema": "ai-ppt-plus/astra-case-iteration/v2",
        "case_id": args.case_id,
        "iteration": args.iteration,
        "pixel_fidelity_score": metrics.get("pixel_fidelity_score"),
        "visual_metrics": metrics,
        "native_editability_valid": native_valid,
        "native_error_count": len(native.get("errors") or []),
        "semantic_accuracy": semantic_accuracy,
        "semantic_audit": {
            "valid": semantic_valid,
            "accuracy": semantic_accuracy,
            "error_count": len(semantic.get("errors") or []),
            "warning_count": len(semantic.get("warnings") or []),
            "expected_object_count": semantic.get("expected_object_count"),
            "audited_object_count": semantic.get("audited_object_count"),
        },
        "inspection_valid": inspect.get("ok") is True,
        "inspection_issue_count": len(inspect.get("issues") or []),
        "repair_action_count": len(executed["report"].get("applied") or []),
        "repair_engine_counts": {
            engine: sum(1 for item in executed["report"].get("applied", []) if item.get("engine") == engine)
            for engine in ("geometry_repair", "typography_repair", "asset_repair", "semantic_repair")
        },
        "asset_resolution_resume": args.resume_after_assets,
        "status": status,
        "artifacts": {
            "layout": str(repaired_layout),
            "pptx": str(pptx),
            "render": str(rendered),
            "visual_comparison": str(visual_report),
            "object_manifest": str(object_manifest),
            "native_editability": str(native_report),
            "semantic_audit": str(semantic_report),
            "inspect": str(inspect_report),
        },
    }
    write_json(out / "iteration-record.json", record)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0 if native_valid and semantic_valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
