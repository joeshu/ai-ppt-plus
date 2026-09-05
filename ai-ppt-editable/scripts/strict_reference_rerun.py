#!/usr/bin/env python3
"""Standard reference-reconstruction rerun entrypoint.

This command always creates a fresh run request, removes any pre-existing output,
executes the repository composer, and writes hash-bound authoring provenance.
It is the mandatory entrypoint for a claimed "rerun" of a fixed reference page.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import uuid
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    parser.add_argument("--source", required=True, help="Original full-page reference image/PDF-page render.")
    parser.add_argument("--layout", required=True)
    parser.add_argument("--out", required=True)
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
    object_manifest = layout.parent / "slide-object-manifest.json"
    imagegen_manifest = layout.parent / "imagegen-assets-manifest.json"
    for required in (page_graph, object_manifest):
        if not required.is_file():
            raise SystemExit(f"required decomposition evidence missing: {required}")

    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    run_dir = project / "strict-reruns" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    current_rerun_path = project / "current-rerun.json"
    if current_rerun_path.exists():
        current_rerun_path.unlink()

    inputs = {
        "source": file_evidence(source),
        "layout": file_evidence(layout),
        "page_graph": file_evidence(page_graph),
        "object_manifest": file_evidence(object_manifest),
    }
    if imagegen_manifest.is_file():
        inputs["imagegen_manifest"] = file_evidence(imagegen_manifest)
    request = {
        "schema": "ai-ppt-plus/strict-rerun-request/v1",
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

    provenance = {
        "schema": "ai-ppt-plus/authoring-provenance/v1",
        "request_id": run_id,
        "entrypoint": "strict_reference_rerun.py",
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "inputs": inputs,
        "deck_path": str(out),
        "deck_sha256": sha256(out),
        "compose_command": command,
    }
    provenance_path = run_dir / "authoring-provenance.json"
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    verify = subprocess.run([
        sys.executable, str(SCRIPT_DIR / "validate_authoring_provenance.py"),
        "--request", str(request_path),
        "--provenance", str(provenance_path),
        "--deck", str(out),
        "--report", str(run_dir / "authoring-provenance-validation.json"),
    ], check=False)
    if verify.returncode != 0:
        raise SystemExit(verify.returncode)

    current_rerun = {
        "schema": "ai-ppt-plus/current-rerun/v1",
        "request_id": run_id,
        "run_request": str(request_path),
        "authoring_provenance": str(provenance_path),
        "deck": str(out),
        "deck_sha256": sha256(out),
        "status": "authored",
    }
    current_rerun_path.write_text(
        json.dumps(current_rerun, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

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
