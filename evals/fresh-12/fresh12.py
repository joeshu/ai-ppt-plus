#!/usr/bin/env python3
"""Prepare, collect, and verify a contamination-resistant Fresh-12 evaluation run.

Fresh-12 is deliberately separate from evals/case-replay-12. Historical
references may be used only after a Fresh-12 run is complete, never as an
input to image generation or editable reconstruction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DEFAULT_SUITE = REPO / "evals" / "case-replay-12" / "case-suite.json"
HISTORICAL_VISUAL_DIR = REPO / "evals" / "case-replay-12" / "visual"
EDITABLE_SCRIPTS = REPO / "ai-ppt-editable" / "scripts"
FORBIDDEN_AUTHORING_MARKERS = (
    "evals/case-replay-12/visual",
    "references/",
    "image2pptx_runs/",
    "run_replay_suite.py",
    "build_layout(",
    "candidate-before",
    "legacy-image-only",
)
REQUIRED_CASE_FILES = (
    "generation/request.json",
    "generation/provenance.json",
    "generation/fresh-original.png",
    "reconstruction/input.json",
    "reconstruction/editable.pptx",
    "render/pptx-render.png",
    "diff/diff.png",
    "diff/visual-compare.json",
    "evidence/editable-objects.json",
    "evidence/pptx-inspection.json",
    "evidence/fresh12-case-evidence.json",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def suite_cases(suite_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    suite = read_json(suite_path)
    cases = [item for item in suite.get("cases", []) if isinstance(item, dict)]
    ids = [str(item.get("case_id", "")) for item in cases]
    if len(cases) != 12 or len(set(ids)) != 12 or any(not item for item in ids):
        raise ValueError("Fresh-12 requires exactly 12 unique case_id values")
    return suite, cases


def iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def contamination_hits(*values: Any) -> list[str]:
    hits: set[str] = set()
    for value in values:
        for raw in iter_strings(value):
            normalized = raw.replace("\\", "/").casefold()
            for marker in FORBIDDEN_AUTHORING_MARKERS:
                if marker.casefold() in normalized:
                    hits.add(marker)
    return sorted(hits)


def prepare(args: argparse.Namespace) -> int:
    suite_path = Path(args.suite).resolve()
    _, cases = suite_cases(suite_path)
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id or f"fresh12-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    manifest_cases = []
    for case in cases:
        case_id = str(case["case_id"])
        case_dir = run_dir / "cases" / case_id
        for part in ("generation", "reconstruction", "render", "diff", "evidence"):
            (case_dir / part).mkdir(parents=True, exist_ok=True)
        prompt = str(case.get("prompt", ""))
        request = {
            "schema": "ai-ppt-plus/fresh12-generation-request/v1",
            "run_id": run_id,
            "case_id": case_id,
            "title": case.get("title"),
            "prompt": prompt,
            "prompt_sha256": text_sha256(prompt),
            "generator_skill": "ai-ppt-visual-gen",
            "generation_policy": "new-raster-required",
            "historical_reference_usage": "forbidden-as-input",
            "case_suite_usage": "generation-and-posthoc-qa-only",
            "required_output": "generation/fresh-original.png",
        }
        write_json(case_dir / "generation" / "request.json", request)
        manifest_cases.append({
            "case_id": case_id,
            "title": case.get("title"),
            "request": str((case_dir / "generation" / "request.json").relative_to(run_dir)),
        })
    manifest = {
        "schema": "ai-ppt-plus/fresh12-run/v1",
        "run_id": run_id,
        "created_at": now_iso(),
        "suite": str(suite_path),
        "suite_sha256": sha256(suite_path),
        "case_count": 12,
        "case_suite_usage": "generation-and-posthoc-qa-only",
        "editable_visual_authority": "current-run-fresh-image-only",
        "historical_reference_usage": "post-verification-comparison-only",
        "forbidden_authoring_markers": list(FORBIDDEN_AUTHORING_MARKERS),
        "required_case_files": list(REQUIRED_CASE_FILES),
        "cases": manifest_cases,
        "status": "AWAITING_FRESH_GENERATION",
    }
    write_json(run_dir / "fresh12-run.json", manifest)
    print(json.dumps({"status": manifest["status"], "run_id": run_id, "run_dir": str(run_dir), "case_count": 12}, ensure_ascii=False))
    return 0


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd or REPO, capture_output=True, text=True, check=False)


def make_diff(reference: Path, rendered: Path, output: Path) -> dict[str, Any]:
    from PIL import Image, ImageChops, ImageStat

    ref = Image.open(reference).convert("RGB")
    candidate = Image.open(rendered).convert("RGB")
    if ref.size != candidate.size:
        candidate = candidate.resize(ref.size, Image.Resampling.LANCZOS)
    diff = ImageChops.difference(ref, candidate)
    output.parent.mkdir(parents=True, exist_ok=True)
    diff.save(output)
    stat = ImageStat.Stat(diff)
    mean = [round(value, 6) for value in stat.mean]
    return {"size": list(ref.size), "mean_abs_channel_diff": mean, "mean_abs_diff": round(sum(mean) / len(mean), 6)}


def collect(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest = read_json(run_dir / "fresh12-run.json")
    case_id = args.case_id
    known = {item.get("case_id") for item in manifest.get("cases", []) if isinstance(item, dict)}
    if case_id not in known:
        raise ValueError(f"unknown Fresh-12 case: {case_id}")
    case_dir = run_dir / "cases" / case_id
    original = case_dir / "generation" / "fresh-original.png"
    provenance = case_dir / "generation" / "provenance.json"
    reconstruction_input = case_dir / "reconstruction" / "input.json"
    if not original.is_file() or not provenance.is_file() or not reconstruction_input.is_file():
        raise ValueError("fresh-original.png, generation/provenance.json and reconstruction/input.json are required before collect")
    pptx_source = Path(args.pptx).resolve()
    if not pptx_source.is_file():
        raise ValueError(f"PPTX not found: {pptx_source}")
    deck = case_dir / "reconstruction" / "editable.pptx"
    if pptx_source != deck:
        shutil.copy2(pptx_source, deck)

    render_dir = case_dir / "render" / "raw"
    render_report = case_dir / "render" / "render-report.json"
    render_cmd = [sys.executable, str(EDITABLE_SCRIPTS / "render_pptx.py"), str(deck), "--output-dir", str(render_dir), "--dpi", "126", "--report", str(render_report)]
    if args.font_dir:
        render_cmd.extend(["--font-dir", str(Path(args.font_dir).resolve())])
    rendered_result = run(render_cmd)
    rendered_candidates = sorted(render_dir.glob("*.png"))
    if rendered_result.returncode != 0 or not rendered_candidates:
        raise RuntimeError(f"render failed: {rendered_result.stdout}\n{rendered_result.stderr}")
    rendered = case_dir / "render" / "pptx-render.png"
    shutil.copy2(rendered_candidates[0], rendered)

    editable_report = case_dir / "evidence" / "editable-objects.json"
    editable_result = run([sys.executable, str(EDITABLE_SCRIPTS / "inspect_editable_objects.py"), str(deck), "--report", str(editable_report)])
    inspect_report = case_dir / "evidence" / "pptx-inspection.json"
    inspect_result = run([sys.executable, str(EDITABLE_SCRIPTS / "inspect_pptx.py"), str(deck), "--report", str(inspect_report)])

    visual_report = case_dir / "diff" / "visual-compare.json"
    visual_result = run([
        sys.executable, str(EDITABLE_SCRIPTS / "compare_visual.py"),
        str(rendered), str(original), "--expected-ratio", "1.7777777778", "--raw-slide", "--report", str(visual_report),
    ])
    diff_metrics = make_diff(original, rendered, case_dir / "diff" / "diff.png")
    editable = read_json(editable_report)
    inspection = read_json(inspect_report)
    visual = read_json(visual_report) if visual_report.is_file() else {"valid": False, "issues": [{"code": "visual_report_missing"}]}
    evidence = {
        "schema": "ai-ppt-plus/fresh12-case-evidence/v1",
        "run_id": manifest.get("run_id"),
        "case_id": case_id,
        "collected_at": now_iso(),
        "fresh_original_sha256": sha256(original),
        "pptx_sha256": sha256(deck),
        "render_sha256": sha256(rendered),
        "diff_sha256": sha256(case_dir / "diff" / "diff.png"),
        "diff_binding": {"reference_sha256": sha256(original), "candidate_sha256": sha256(rendered)},
        "diff_metrics": diff_metrics,
        "editable_object_evidence": {
            "valid": bool(editable.get("valid")),
            "observed_shape_count": editable.get("observed_shape_count", 0),
            "whole_slide_pictures": editable.get("whole_slide_pictures", []),
        },
        "pptx_structure": {
            "ok": bool(inspection.get("ok")),
            "slides": inspection.get("slides", []),
            "issues": inspection.get("issues", []),
        },
        "visual_compare": {"valid": bool(visual.get("valid")), "metrics": visual.get("metrics", {}), "issues": visual.get("issues", [])},
        "collector_exit_codes": {"render": rendered_result.returncode, "editable_objects": editable_result.returncode, "inspect": inspect_result.returncode, "visual_compare": visual_result.returncode},
    }
    write_json(case_dir / "evidence" / "fresh12-case-evidence.json", evidence)
    print(json.dumps({"case_id": case_id, "collected": True, "visual_valid": evidence["visual_compare"]["valid"], "editable_valid": evidence["editable_object_evidence"]["valid"]}, ensure_ascii=False))
    return 0


def historical_hashes(directory: Path) -> set[str]:
    if not directory.is_dir():
        return set()
    return {sha256(path) for path in directory.glob("*reference*.png") if path.is_file()}


def verify_case(run_id: str, case_id: str, case_dir: Path, old_hashes: set[str]) -> dict[str, Any]:
    failures: list[str] = []
    missing = [name for name in REQUIRED_CASE_FILES if not (case_dir / name).is_file()]
    if missing:
        failures.extend(f"missing:{name}" for name in missing)
        return {"case_id": case_id, "status": "INCOMPLETE", "failures": failures, "missing": missing}

    request = read_json(case_dir / "generation" / "request.json")
    provenance = read_json(case_dir / "generation" / "provenance.json")
    reconstruction = read_json(case_dir / "reconstruction" / "input.json")
    editable = read_json(case_dir / "evidence" / "editable-objects.json")
    inspection = read_json(case_dir / "evidence" / "pptx-inspection.json")
    visual = read_json(case_dir / "diff" / "visual-compare.json")
    case_evidence = read_json(case_dir / "evidence" / "fresh12-case-evidence.json")
    original = case_dir / "generation" / "fresh-original.png"
    deck = case_dir / "reconstruction" / "editable.pptx"
    rendered = case_dir / "render" / "pptx-render.png"
    diff = case_dir / "diff" / "diff.png"
    original_hash = sha256(original)
    deck_hash = sha256(deck)
    rendered_hash = sha256(rendered)
    diff_hash = sha256(diff)

    if original_hash in old_hashes:
        failures.append("fresh_original_matches_historical_reference")
    if request.get("run_id") != run_id or request.get("case_id") != case_id:
        failures.append("generation_request_identity_mismatch")
    if provenance.get("run_id") != run_id or provenance.get("case_id") != case_id:
        failures.append("generation_provenance_identity_mismatch")
    prov_hash = provenance.get("generated_image_sha256") or provenance.get("source_image_sha256") or provenance.get("sha256")
    if prov_hash != original_hash:
        failures.append("generation_provenance_hash_mismatch")
    if provenance.get("generator_skill") not in {"ai-ppt-visual-gen", "native-image-generation", "image_gen"}:
        failures.append("generation_backend_not_native_imagegen")

    expected_reconstruction = {
        "run_id": run_id,
        "case_id": case_id,
        "visual_input_authority": "fresh-image-only",
        "source_image_sha256": original_hash,
        "layout_source": "image-analysis",
        "case_spec_usage": "generation-and-posthoc-qa-only",
    }
    for key, expected in expected_reconstruction.items():
        if reconstruction.get(key) != expected:
            failures.append(f"reconstruction_contract_mismatch:{key}")
    hits = contamination_hits(reconstruction)
    if hits:
        failures.append("forbidden_authoring_input:" + ",".join(hits))

    if case_evidence.get("fresh_original_sha256") != original_hash:
        failures.append("case_evidence_source_hash_mismatch")
    if case_evidence.get("pptx_sha256") != deck_hash:
        failures.append("case_evidence_pptx_hash_mismatch")
    if case_evidence.get("render_sha256") != rendered_hash:
        failures.append("case_evidence_render_hash_mismatch")
    if case_evidence.get("diff_sha256") != diff_hash:
        failures.append("case_evidence_diff_hash_mismatch")
    binding = case_evidence.get("diff_binding") or {}
    if binding.get("reference_sha256") != original_hash or binding.get("candidate_sha256") != rendered_hash:
        failures.append("diff_not_bound_to_fresh_source_and_current_render")

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
    if not visual.get("valid"):
        failures.append("visual_fidelity_gate_failed")

    return {
        "case_id": case_id,
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "hashes": {"fresh_original": original_hash, "pptx": deck_hash, "render": rendered_hash, "diff": diff_hash},
        "visual_metrics": visual.get("metrics", {}),
        "editable_shape_count": editable.get("observed_shape_count", 0),
        "native_text_objects": slides[0].get("text_objects", 0) if slides else 0,
    }


def verify(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest = read_json(run_dir / "fresh12-run.json")
    suite_path = Path(args.suite).resolve()
    _, cases = suite_cases(suite_path)
    expected_ids = [str(item["case_id"]) for item in cases]
    manifest_ids = [str(item.get("case_id")) for item in manifest.get("cases", []) if isinstance(item, dict)]
    run_id = str(manifest.get("run_id", ""))
    failures: list[str] = []
    if manifest.get("suite_sha256") != sha256(suite_path):
        failures.append("suite_hash_changed")
    if manifest_ids != expected_ids:
        failures.append("case_matrix_mismatch")
    old_hashes = historical_hashes(Path(args.historical_dir).resolve())
    results = [verify_case(run_id, case_id, run_dir / "cases" / case_id, old_hashes) for case_id in expected_ids]
    incomplete = [item for item in results if item["status"] == "INCOMPLETE"]
    failed = [item for item in results if item["status"] == "FAIL"]
    if incomplete:
        verdict = "INCOMPLETE"
    elif failures or failed:
        verdict = "FAIL"
    else:
        verdict = "PASS"
    report = {
        "schema": "ai-ppt-plus/fresh12-evaluation/v1",
        "run_id": run_id,
        "verified_at": now_iso(),
        "verdict": verdict,
        "case_count": 12,
        "complete_cases": sum(item["status"] != "INCOMPLETE" for item in results),
        "passed_cases": sum(item["status"] == "PASS" for item in results),
        "failed_cases": len(failed),
        "incomplete_cases": len(incomplete),
        "global_failures": failures,
        "historical_reference_hash_count": len(old_hashes),
        "historical_references_used_as_authoring_input": False,
        "historical_comparison_eligible": verdict in {"PASS", "FAIL"} and not incomplete,
        "capability_judgement_allowed": verdict in {"PASS", "FAIL"} and not incomplete,
        "cases": results,
    }
    write_json(Path(args.report).resolve() if args.report else run_dir / "fresh12-evaluation.json", report)
    print(json.dumps({key: report[key] for key in ("verdict", "complete_cases", "passed_cases", "failed_cases", "incomplete_cases", "capability_judgement_allowed")}, ensure_ascii=False))
    if args.strict and verdict != "PASS":
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="create a clean 12-case run contract and generation requests")
    p.add_argument("--suite", default=str(DEFAULT_SUITE))
    p.add_argument("--run-dir", required=True)
    p.add_argument("--run-id")
    p.set_defaults(func=prepare)
    p = sub.add_parser("collect", help="collect render, diff and editability evidence for one genuinely reconstructed case")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--case-id", required=True)
    p.add_argument("--pptx", required=True)
    p.add_argument("--font-dir")
    p.set_defaults(func=collect)
    p = sub.add_parser("verify", help="verify 12/12 current-run evidence and reject historical contamination")
    p.add_argument("--suite", default=str(DEFAULT_SUITE))
    p.add_argument("--run-dir", required=True)
    p.add_argument("--historical-dir", default=str(HISTORICAL_VISUAL_DIR))
    p.add_argument("--report")
    p.add_argument("--strict", action="store_true")
    p.set_defaults(func=verify)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
