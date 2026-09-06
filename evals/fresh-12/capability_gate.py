#!/usr/bin/env python3
"""Final Fresh-12 capability gate.

This is intentionally stricter than the structural `fresh12.py verify` preflight.
A capability verdict is allowed only after all 12 current-run cases contain the
fresh source, reconstructed PPTX, render, diff, editable-object evidence, and
current-run PageGraph provenance. Historical references are hash checked but
never accepted as authoring inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DEFAULT_HISTORICAL = REPO / "evals" / "case-replay-12" / "visual"
FORBIDDEN = (
    "evals/case-replay-12/visual",
    "references/",
    "image2pptx_runs/",
    "run_replay_suite.py",
    "build_layout(",
    "candidate-before",
    "legacy-image-only",
)
REQUIRED = (
    "generation/request.json",
    "generation/provenance.json",
    "generation/fresh-original.png",
    "reconstruction/input.json",
    "reconstruction/editable.pptx",
    "reconstruction/pagegraph.json",
    "reconstruction/pagegraph-provenance.json",
    "render/pptx-render.png",
    "diff/diff.png",
    "diff/visual-compare.json",
    "evidence/editable-objects.json",
    "evidence/pptx-inspection.json",
    "evidence/fresh12-case-evidence.json",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_time(value: Any) -> datetime:
    text = str(value or "").replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def contamination(value: Any) -> list[str]:
    found: set[str] = set()
    for raw in strings(value):
        normalized = raw.replace("\\", "/").casefold()
        for marker in FORBIDDEN:
            if marker.casefold() in normalized:
                found.add(marker)
    return sorted(found)


def historical_hashes(path: Path) -> set[str]:
    if not path.is_dir():
        return set()
    return {sha256(item) for item in path.glob("*reference*.png") if item.is_file()}


def pagegraph_failures(provenance: dict[str, Any], request_id: str, source_hash: str, pagegraph_hash: str) -> list[str]:
    failures: list[str] = []
    if provenance.get("schema") != "ai-ppt-plus/page-graph-provenance/v1":
        failures.append("pagegraph_provenance_schema_invalid")
    if not request_id or provenance.get("request_id") != request_id:
        failures.append("pagegraph_request_id_mismatch")
    producer = provenance.get("producer") if isinstance(provenance.get("producer"), dict) else {}
    if producer.get("task") != "visual-reconstruction":
        failures.append("pagegraph_producer_task_invalid")
    source = provenance.get("source") if isinstance(provenance.get("source"), dict) else {}
    pagegraph = provenance.get("page_graph") if isinstance(provenance.get("page_graph"), dict) else {}
    if source.get("sha256") != source_hash:
        failures.append("pagegraph_source_hash_mismatch")
    if pagegraph.get("sha256") != pagegraph_hash:
        failures.append("pagegraph_hash_mismatch")
    return failures


def evaluate_case(
    run_dir: Path,
    run_id: str,
    created_at: datetime,
    case_id: str,
    old_hashes: set[str],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    case_dir = run_dir / "cases" / case_id
    missing = [relative for relative in REQUIRED if not (case_dir / relative).is_file()]
    if missing:
        return {"case_id": case_id, "status": "INCOMPLETE", "missing": missing, "failures": [f"missing:{item}" for item in missing]}

    request = read_json(case_dir / "generation/request.json")
    generation = read_json(case_dir / "generation/provenance.json")
    reconstruction = read_json(case_dir / "reconstruction/input.json")
    visual = read_json(case_dir / "diff/visual-compare.json")
    editable = read_json(case_dir / "evidence/editable-objects.json")
    inspection = read_json(case_dir / "evidence/pptx-inspection.json")
    evidence = read_json(case_dir / "evidence/fresh12-case-evidence.json")
    pagegraph_provenance = read_json(case_dir / "reconstruction/pagegraph-provenance.json")

    source = case_dir / "generation/fresh-original.png"
    deck = case_dir / "reconstruction/editable.pptx"
    pagegraph = case_dir / "reconstruction/pagegraph.json"
    rendered = case_dir / "render/pptx-render.png"
    diff = case_dir / "diff/diff.png"
    source_hash = sha256(source)
    deck_hash = sha256(deck)
    pagegraph_hash = sha256(pagegraph)
    render_hash = sha256(rendered)
    diff_hash = sha256(diff)
    failures: list[str] = []

    if source_hash in old_hashes:
        failures.append("fresh_source_matches_historical_reference")
    if request.get("run_id") != run_id or request.get("case_id") != case_id:
        failures.append("generation_request_identity_mismatch")
    if request.get("generation_policy") != "new-raster-required":
        failures.append("generation_request_not_fresh")
    if request.get("historical_reference_usage") != "forbidden-as-input":
        failures.append("historical_input_policy_not_forbidden")
    if generation.get("run_id") != run_id or generation.get("case_id") != case_id:
        failures.append("generation_provenance_identity_mismatch")
    if generation.get("prompt_sha256") != request.get("prompt_sha256"):
        failures.append("generation_prompt_hash_mismatch")
    if not generation.get("generation_id"):
        failures.append("generation_id_missing")
    try:
        if parse_time(generation.get("generated_at")) < created_at:
            failures.append("generation_predates_fresh12_run")
    except Exception:
        failures.append("generation_timestamp_invalid")
    generated_hash = generation.get("generated_image_sha256") or generation.get("source_image_sha256") or generation.get("sha256")
    if generated_hash != source_hash:
        failures.append("generation_source_hash_mismatch")
    if generation.get("generator_skill") not in {"ai-ppt-visual-gen", "native-image-generation", "image_gen"}:
        failures.append("generation_backend_not_native_imagegen")

    expected = {
        "run_id": run_id,
        "case_id": case_id,
        "visual_input_authority": "fresh-image-only",
        "source_image_sha256": source_hash,
        "layout_source": "image-analysis",
        "case_spec_usage": "generation-and-posthoc-qa-only",
    }
    for key, wanted in expected.items():
        if reconstruction.get(key) != wanted:
            failures.append(f"reconstruction_contract_mismatch:{key}")
    hits = contamination({"generation": generation, "reconstruction": reconstruction})
    if hits:
        failures.append("forbidden_authoring_input:" + ",".join(hits))

    request_id = str(reconstruction.get("request_id") or "")
    failures.extend(pagegraph_failures(pagegraph_provenance, request_id, source_hash, pagegraph_hash))

    if evidence.get("fresh_original_sha256") != source_hash:
        failures.append("evidence_source_hash_mismatch")
    if evidence.get("pptx_sha256") != deck_hash:
        failures.append("evidence_pptx_hash_mismatch")
    if evidence.get("render_sha256") != render_hash:
        failures.append("evidence_render_hash_mismatch")
    if evidence.get("diff_sha256") != diff_hash:
        failures.append("evidence_diff_hash_mismatch")
    binding = evidence.get("diff_binding") if isinstance(evidence.get("diff_binding"), dict) else {}
    if binding.get("reference_sha256") != source_hash or binding.get("candidate_sha256") != render_hash:
        failures.append("diff_not_bound_to_current_source_and_render")

    if not editable.get("valid"):
        failures.append("editable_object_audit_invalid")
    if int(editable.get("observed_shape_count") or 0) <= 1:
        failures.append("insufficient_editable_objects")
    if editable.get("whole_slide_pictures"):
        failures.append("whole_slide_picture_present")
    if not inspection.get("ok"):
        failures.append("pptx_inspection_failed")
    slides = [item for item in inspection.get("slides", []) if isinstance(item, dict)]
    if len(slides) != 1:
        failures.append("expected_single_slide")
    elif int(slides[0].get("text_objects") or 0) <= 0:
        failures.append("no_native_text_objects")
    if any(item.get("code") == "possible_full_slide_flattening" for item in inspection.get("issues", []) if isinstance(item, dict)):
        failures.append("possible_full_slide_flattening")

    metrics = visual.get("metrics") if isinstance(visual.get("metrics"), dict) else {}
    for metric, threshold in thresholds.items():
        observed = metrics.get(metric)
        if not isinstance(observed, (int, float)) or float(observed) < float(threshold):
            failures.append(f"visual_metric_below_gate:{metric}")

    return {
        "case_id": case_id,
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "hashes": {"source": source_hash, "pptx": deck_hash, "pagegraph": pagegraph_hash, "render": render_hash, "diff": diff_hash},
        "visual_metrics": metrics,
        "editable_shape_count": editable.get("observed_shape_count", 0),
        "native_text_objects": slides[0].get("text_objects", 0) if slides else 0,
    }


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    manifest = read_json(run_dir / "fresh12-run.json")
    cases = [item for item in manifest.get("cases", []) if isinstance(item, dict)]
    case_ids = [str(item.get("case_id") or "") for item in cases]
    global_failures: list[str] = []
    if len(case_ids) != 12 or len(set(case_ids)) != 12 or any(not item for item in case_ids):
        global_failures.append("fresh12_manifest_must_contain_exactly_12_unique_cases")
    run_id = str(manifest.get("run_id") or "")
    try:
        created_at = parse_time(manifest.get("created_at"))
    except Exception:
        created_at = datetime.max.replace(tzinfo=timezone.utc)
        global_failures.append("run_created_at_invalid")
    thresholds = {
        "blurred_layout_ssim": float(args.blurred_layout_ssim_min),
        "global_ssim": float(args.global_ssim_min),
        "pixel_fidelity_score": float(args.pixel_fidelity_score_min),
    }
    old_hashes = historical_hashes(Path(args.historical_dir).resolve())
    results = [evaluate_case(run_dir, run_id, created_at, case_id, old_hashes, thresholds) for case_id in case_ids]
    incomplete = [item for item in results if item.get("status") == "INCOMPLETE"]
    complete = len(results) == 12 and not incomplete
    source_hashes = [item.get("hashes", {}).get("source") for item in results if item.get("status") != "INCOMPLETE"]
    duplicates = sorted({item for item in source_hashes if item and source_hashes.count(item) > 1})
    if duplicates:
        global_failures.append("duplicate_fresh_source_images_across_cases")
    failed = [item for item in results if item.get("status") == "FAIL"]
    if not complete:
        verdict = "INCOMPLETE"
    elif global_failures or failed:
        verdict = "FAIL"
    else:
        verdict = "PASS"
    return {
        "schema": "ai-ppt-plus/fresh12-capability-gate/v1",
        "run_id": run_id,
        "verified_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": verdict,
        "thresholds": thresholds,
        "case_count": 12,
        "complete_cases": sum(item.get("status") != "INCOMPLETE" for item in results),
        "passed_cases": sum(item.get("status") == "PASS" for item in results),
        "failed_cases": len(failed),
        "incomplete_cases": len(incomplete),
        "global_failures": global_failures,
        "historical_reference_hash_count": len(old_hashes),
        "historical_references_used_as_authoring_input": False,
        "capability_judgement_allowed": complete,
        "historical_comparison_eligible": complete,
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--historical-dir", default=str(DEFAULT_HISTORICAL))
    parser.add_argument("--blurred-layout-ssim-min", type=float, default=0.90)
    parser.add_argument("--global-ssim-min", type=float, default=0.82)
    parser.add_argument("--pixel-fidelity-score-min", type=float, default=0.80)
    parser.add_argument("--report")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        report = evaluate(args)
    except Exception as exc:
        report = {
            "schema": "ai-ppt-plus/fresh12-capability-gate/v1",
            "verdict": "ERROR",
            "capability_judgement_allowed": False,
            "global_failures": [f"{type(exc).__name__}: {exc}"],
        }
    output = Path(args.report).resolve() if args.report else Path(args.run_dir).resolve() / "fresh12-capability-verdict.json"
    write_json(output, report)
    print(json.dumps({key: report.get(key) for key in ("verdict", "complete_cases", "passed_cases", "failed_cases", "incomplete_cases", "capability_judgement_allowed")}, ensure_ascii=False))
    return 0 if (report.get("verdict") == "PASS" or (not args.strict and report.get("verdict") in {"FAIL", "INCOMPLETE"})) else 2


if __name__ == "__main__":
    raise SystemExit(main())
