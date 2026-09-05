#!/usr/bin/env python3
"""Reference P0 repair entrypoint; final output remains pending visual review.

plan.json: reference, inventory, graph, layout, typography[], assets[],
solve_relations (bool), locked_ids[]. Paths resolve relative to plan.json.
Asset jobs require generated path, approved alpha reference, QA v2 and target
bbox in inches. No original crop is silently promoted into a final asset.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reconstruction.graph_ir import PageGraph
from reconstruction.source_coverage import audit_source_coverage, extract_pptx_objects
from reconstruction.repair_executors import execute_typography_search, _locate
from reconstruction.render_measure import measure_text
from reconstruction.relation_geometry import solve_graph_relations
from reconstruction.asset_subject import subject_placement
from reconstruction.asset_metrics import compare_asset_subjects
from reconstruction.asset_quality_qa import parse_asset_quality_response
from authoring_backend import build_pptx, build_with_embedded_fonts
from reference_preflight import validate_reference_preflight


def run(plan_path, output_dir):
    plan_path, output_dir = Path(plan_path).resolve(), Path(output_dir).resolve()
    base = plan_path.parent
    load = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
    plan = load(plan_path)
    resolve = lambda name: (base / plan[name]).resolve()
    reference = resolve("reference")
    inventory = load(resolve("inventory"))
    graph = PageGraph.from_dict(load(resolve("graph")))
    if sha256(reference.read_bytes()).hexdigest() != inventory.get("source_sha256"):
        raise ValueError("inventory does not match actual reference bytes")
    coverage = audit_source_coverage(inventory, graph)
    if not coverage["valid"]:
        raise ValueError(coverage["errors"])
    deck = load(resolve("layout"))
    if len(deck.get("slides", [])) != 1:
        raise ValueError("one reference page per P0 run required")
    route_path = resolve("layout").parent / "route-decision.json"
    if not route_path.is_file() or load(route_path).get("route") != "reference-reconstruction":
        raise ValueError("explicit reference route required")
    if resolve("graph") != resolve("layout").parent / "page-graph.json":
        raise ValueError("graph must be the canonical preflight page-graph.json")
    if deck.get("units", "fraction") != "fraction":
        raise ValueError("P0 repair input must use fraction geometry")
    deck["assets_dir"] = str((resolve("layout").parent / deck.get("assets_dir", ".")).resolve())
    reports = {"source_coverage": coverage, "typography": [], "assets": []}
    if plan.get("solve_relations"):
        solved = solve_graph_relations(graph, locked_ids=plan.get("locked_ids", []))
        for identifier in solved["applied"]:
            _locate(deck, identifier)[1].update(dict(zip(("x", "y", "w", "h"), solved["boxes"][identifier])))
        reports["relations"] = solved
    for job in plan.get("typography", []):
        if job["object_id"] in plan.get("locked_ids", []):
            raise ValueError("typography job targets accepted lock")
        result = execute_typography_search(deck, job["object_id"], job["target"], job["patches"],
                                           measure_text, budget=job.get("budget", 12), tolerance=job.get("tolerance", .002))
        if not result["report"]["valid"]:
            raise ValueError(f"typography remains unaccepted: {job['object_id']}")
        reports["typography"].append(result["report"])
        deck = result["deck"]
    for job in plan.get("assets", []):
        if job["object_id"] in plan.get("locked_ids", []):
            raise ValueError("asset job targets accepted lock")
        if job.get("source") != "native-imagegen":
            raise ValueError("asset job must retain native-imagegen provenance")
        path = (base / job["path"]).resolve()
        qa = load(base / job["qa"])
        if qa.get("candidate_sha256") != sha256(path.read_bytes()).hexdigest():
            raise ValueError("asset QA refers to different candidate bytes")
        evaluated = parse_asset_quality_response(qa, expected_object_id=job["object_id"])
        if not evaluated["approved"]:
            raise ValueError("asset requires generation/review; no automatic fallback")
        metrics = compare_asset_subjects(base / job["alpha_reference"], path)
        threshold = job.get("min_silhouette_iou", .9)
        if not isinstance(threshold, (float, int)) or not .9 <= threshold <= 1:
            raise ValueError("silhouette threshold cannot lower the P0 floor")
        if qa.get("reference_sha256") != metrics["reference_sha256"]:
            raise ValueError("asset QA reference hash mismatch")
        if metrics["silhouette_iou"] < threshold:
            raise ValueError("asset silhouette below threshold")
        placement = subject_placement(path, job["target_bbox_inches"])
        collection, item = _locate(deck, job["object_id"])
        if collection != "icons":
            raise ValueError("asset subject repair only supports independent icons")
        x, y, w, h = placement["image_bbox"]
        sw, sh = deck["slide_width_in"], deck["slide_height_in"]
        item.update({"file": str(path), "x": x / sw, "y": y / sh, "w": w / sw, "h": h / sh})
        reports["assets"].append({"placement": placement, "metrics": metrics, "qa": evaluated})
    font_dir = str(resolve("font_dir")) if plan.get("font_dir") else None
    font_manifest = str(resolve("font_manifest")) if plan.get("font_manifest") else None
    embed = bool(plan.get("embed_fonts"))
    preflight = validate_reference_preflight(resolve("layout"), deck, embed_fonts=embed,
                                            font_dir=font_dir, font_manifest=font_manifest)
    if not preflight["valid"]:
        raise ValueError(preflight["issues"])
    output_dir.mkdir(parents=True, exist_ok=False)
    pptx = output_dir / "candidate.pptx"
    if embed:
        build_with_embedded_fonts(deck, pptx, font_dir=font_dir, font_manifest=font_manifest,
                                  embedding_report=output_dir / "fonts.json")
    else:
        build_pptx(deck, pptx)
    final = audit_source_coverage(inventory, graph, extract_pptx_objects(str(pptx)))
    if not final["valid"]:
        raise ValueError(final["errors"])
    subprocess.run([sys.executable, str(ROOT / "scripts/render_pptx.py"), str(pptx),
                    "--output-dir", str(output_dir / "render"), "--report", str(output_dir / "render.json")],
                   check=True, timeout=180)
    reports.update({"final_coverage": final, "deck_sha256": sha256(pptx.read_bytes()).hexdigest(),
                    "status": "pending-visual-review", "release_eligible": False})
    (output_dir / "repair-report.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    run(args.plan, args.output_dir)
