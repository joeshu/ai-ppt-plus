#!/usr/bin/env python3
"""Standard provenance-bound reference-reconstruction rerun entrypoint.

A strict rerun may only compose a deck from a PageGraph and generated assets
that carry the same current request_id. The final deck is then checked to prove
that approved ImageGen bytes are the bytes actually embedded in ppt/media.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_evidence(path: Path) -> dict:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return {"path": str(resolved), "sha256": sha256(resolved)}


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def run_validator(command: list[str], label: str) -> None:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        if completed.stdout:
            print(completed.stdout, file=sys.stderr)
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)
        raise SystemExit(f"{label} failed with exit code {completed.returncode}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    parser.add_argument("--source", required=True, help="Original full-page reference image/PDF-page render.")
    parser.add_argument("--layout", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--request-id", help="Expected current transaction id; must match PageGraph/ImageGen evidence.")
    parser.add_argument("--font-dir")
    parser.add_argument("--font-manifest")
    parser.add_argument("--preview-dir")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    project = Path(args.project).resolve()
    project.mkdir(parents=True, exist_ok=True)
    source = Path(args.source).resolve()
    layout = Path(args.layout).resolve()
    out = Path(args.out).resolve()
    if not source.is_file() or not layout.is_file():
        raise SystemExit("source/layout must exist")
    if out.exists() and not args.overwrite:
        raise SystemExit(f"refusing to reuse existing output; pass --overwrite for a fresh rerun: {out}")

    route_path = layout.parent / "route-decision.json"
    route = load_json(route_path) if route_path.is_file() else {}
    if route.get("route") != "reference-reconstruction":
        raise SystemExit("strict_reference_rerun requires route=reference-reconstruction")

    page_graph = layout.parent / "page-graph.json"
    page_graph_provenance = layout.parent / "page-graph-provenance.json"
    object_manifest = layout.parent / "slide-object-manifest.json"
    imagegen_manifest = layout.parent / "imagegen-assets-manifest.json"
    for required in (page_graph, page_graph_provenance, object_manifest):
        if not required.is_file():
            raise SystemExit(f"required current-run decomposition evidence missing: {required}")

    graph_provenance = load_json(page_graph_provenance)
    graph_request_id = graph_provenance.get("request_id")
    if not isinstance(graph_request_id, str) or not graph_request_id.strip():
        raise SystemExit("page-graph-provenance.json must declare current request_id")
    run_id = graph_request_id.strip()
    if args.request_id and args.request_id != run_id:
        raise SystemExit("--request-id does not match PageGraph provenance request_id")

    imagegen_data = load_json(imagegen_manifest) if imagegen_manifest.is_file() else None
    if imagegen_data is not None and imagegen_data.get("request_id") != run_id:
        raise SystemExit("imagegen-assets-manifest.json request_id does not match PageGraph/current rerun")

    started_at = datetime.now(timezone.utc).isoformat()
    run_dir = project / "strict-reruns" / run_id
    if run_dir.exists():
        raise SystemExit(f"request_id has already been used; refusing transaction reuse: {run_id}")
    run_dir.mkdir(parents=True, exist_ok=False)
    current_rerun_path = project / "current-rerun.json"
    if current_rerun_path.exists():
        current_rerun_path.unlink()

    graph_report = run_dir / "page-graph-provenance-validation.json"
    run_validator([
        sys.executable, str(SCRIPT_DIR / "validate_page_graph_provenance.py"),
        "--provenance", str(page_graph_provenance),
        "--request-id", run_id,
        "--source", str(source),
        "--page-graph", str(page_graph),
        "--report", str(graph_report),
    ], "PageGraph provenance validation")

    imagegen_run_report = None
    if imagegen_manifest.is_file():
        imagegen_run_report = run_dir / "current-run-imagegen-validation.json"
        run_validator([
            sys.executable, str(SCRIPT_DIR / "validate_current_run_imagegen.py"),
            "--manifest", str(imagegen_manifest),
            "--request-id", run_id,
            "--report", str(imagegen_run_report),
        ], "current-run ImageGen validation")

    inputs = {
        "source": file_evidence(source),
        "layout": file_evidence(layout),
        "page_graph": file_evidence(page_graph),
        "page_graph_provenance": file_evidence(page_graph_provenance),
        "object_manifest": file_evidence(object_manifest),
    }
    if imagegen_manifest.is_file():
        inputs["imagegen_manifest"] = file_evidence(imagegen_manifest)
    request = {
        "schema": "ai-ppt-plus/strict-rerun-request/v2",
        "request_id": run_id,
        "created_at": started_at,
        "entrypoint": "strict_reference_rerun.py",
        "inputs": inputs,
        "requested_output": str(out),
    }
    request_path = run_dir / "run-request.json"
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if out.exists():
        out.unlink()
    out.parent.mkdir(parents=True, exist_ok=True)

    command = [sys.executable, str(SCRIPT_DIR / "compose_pptx.py"), str(layout), str(out), "--strict-input", "--require-native-structure", "--embed-fonts"]
    if args.font_dir:
        command += ["--font-dir", str(Path(args.font_dir).resolve())]
    if args.font_manifest:
        command += ["--font-manifest", str(Path(args.font_manifest).resolve())]
    if args.preview_dir:
        command += ["--preview-dir", str(Path(args.preview_dir).resolve())]
    started_ns = time.time_ns()
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    (run_dir / "compose.stdout.txt").write_text(completed.stdout or "", encoding="utf-8")
    (run_dir / "compose.stderr.txt").write_text(completed.stderr or "", encoding="utf-8")
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    if not out.is_file():
        raise SystemExit("composer returned success but output deck is missing")
    if out.stat().st_mtime_ns < started_ns:
        raise SystemExit("output deck is not fresh for this rerun")

    embedded_asset_report = None
    if imagegen_manifest.is_file():
        embedded_asset_report = run_dir / "embedded-imagegen-assets-validation.json"
        run_validator([
            sys.executable, str(SCRIPT_DIR / "validate_embedded_imagegen_assets.py"),
            "--pptx", str(out),
            "--manifest", str(imagegen_manifest),
            "--request-id", run_id,
            "--report", str(embedded_asset_report),
        ], "embedded ImageGen asset validation")

    provenance = {
        "schema": "ai-ppt-plus/authoring-provenance/v2",
        "request_id": run_id,
        "entrypoint": "strict_reference_rerun.py",
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "inputs": inputs,
        "deck_path": str(out),
        "deck_sha256": sha256(out),
        "compose_command": command,
        "gates": {
            "page_graph_provenance": str(graph_report),
            "current_run_imagegen": str(imagegen_run_report) if imagegen_run_report else None,
            "embedded_imagegen_assets": str(embedded_asset_report) if embedded_asset_report else None,
        },
    }
    provenance_path = run_dir / "authoring-provenance.json"
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    authoring_report = run_dir / "authoring-provenance-validation.json"
    run_validator([
        sys.executable, str(SCRIPT_DIR / "validate_authoring_provenance.py"),
        "--request", str(request_path),
        "--provenance", str(provenance_path),
        "--deck", str(out),
        "--report", str(authoring_report),
    ], "authoring provenance validation")

    current_rerun = {
        "schema": "ai-ppt-plus/current-rerun/v2",
        "request_id": run_id,
        "run_request": str(request_path),
        "authoring_provenance": str(provenance_path),
        "page_graph_provenance_validation": str(graph_report),
        "current_run_imagegen_validation": str(imagegen_run_report) if imagegen_run_report else None,
        "embedded_imagegen_assets_validation": str(embedded_asset_report) if embedded_asset_report else None,
        "deck": str(out),
        "deck_sha256": sha256(out),
        "status": "authored-and-asset-verified",
    }
    current_rerun_path.write_text(json.dumps(current_rerun, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": "ok",
        "request_id": run_id,
        "deck": str(out),
        "run_dir": str(run_dir),
        "provenance": str(provenance_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
