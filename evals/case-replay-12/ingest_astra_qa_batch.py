#!/usr/bin/env python3
"""Ingest Astra QA responses for the real 12-case replay suite.

Expected layout:
  <batch-dir>/<case-id>/page-graph.json
  <batch-dir>/<case-id>/deterministic-difference-graph.json
  <responses-dir>/<case-id>.json

Produces merged DifferenceGraph, bounded RepairPlan and iteration records without
executing PPTX mutations. Execution remains the deterministic engine's job.
"""
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

from reconstruction.batch_ingestion import ingest_astra_qa
from reconstruction.difference_graph import DifferenceGraph
from reconstruction.graph_ir import PageGraph
from reconstruction.astra_contract import parse_visual_qa_response


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-dir", type=Path, default=ROOT / "astra-closed-loop")
    parser.add_argument("--responses-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "astra-closed-loop-ingested")
    parser.add_argument("--iteration", type=int, default=1)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary_path = args.batch_dir / "summary.json"
    batch_summary = read_json(summary_path)
    cases = batch_summary.get("cases") or []
    results = []
    missing = []

    for case in cases:
        case_id = case["case_id"]
        response_path = args.responses_dir / f"{case_id}.json"
        if not response_path.is_file():
            missing.append(case_id)
            continue

        case_dir = args.batch_dir / case_id
        page_graph = PageGraph.from_dict(read_json(case_dir / "page-graph.json"))
        deterministic = DifferenceGraph.from_dict(read_json(case_dir / "deterministic-difference-graph.json"))
        astra = parse_visual_qa_response(read_json(response_path))
        ingested = ingest_astra_qa(page_graph=page_graph, deterministic_graph=deterministic, astra_graph=astra)

        output_case = args.output_dir / case_id / f"iteration-{args.iteration}"
        write_json(output_case / "merged-difference-graph.json", ingested["merged_difference_graph"])
        write_json(output_case / "repair-plan.json", ingested["repair_plan"])
        visual_metrics = dict(case.get("visual_metrics") or {})
        record = {
            "schema": "ai-ppt-plus/astra-case-iteration/v1",
            "case_id": case_id,
            "iteration": args.iteration,
            "pixel_fidelity_score": visual_metrics.get("pixel_fidelity_score"),
            **ingested["summary"],
            "status": (
                "external-asset"
                if ingested["summary"]["requires_external_asset"]
                else "blocked"
                if ingested["summary"]["blocking_deferred"]
                else "repair-ready"
                if ingested["summary"]["repair_action_count"]
                else "gate-ready"
            ),
        }
        write_json(output_case / "iteration-record.json", record)
        results.append(record)

    if args.strict and missing:
        raise SystemExit("missing Astra QA responses: " + ", ".join(missing))

    batch_out = {
        "schema": "ai-ppt-plus/astra-ingestion-batch/v1",
        "iteration": args.iteration,
        "case_count": len(results),
        "missing_cases": missing,
        "status_counts": {status: sum(1 for item in results if item["status"] == status) for status in sorted({item["status"] for item in results})},
        "cases": results,
    }
    write_json(args.output_dir / f"iteration-{args.iteration}-summary.json", batch_out)
    print(json.dumps(batch_out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
