#!/usr/bin/env python3
"""Normalize image/PPTX inputs into a reviewable distillation case.

The operator supplies only source files.  This command copies them into an
immutable, hash-bound case directory, optionally renders PPTX pages into
reference images, and writes a draft registry entry.  It never approves a
candidate or invents training labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atomic_output import atomic_copy, atomic_write_json


REGISTRY_SCHEMA = "ai-ppt-plus/distillation-case-registry/v1"
INTAKE_SCHEMA = "ai-ppt-plus/distillation-case-intake/v1"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return value or "source"


def ref(path: Path, *, role: str, root: Path, source_name: str | None = None) -> dict[str, Any]:
    return {
        "role": role,
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256(path),
        "source_name": source_name or path.name,
    }


def load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": REGISTRY_SCHEMA, "version": 1, "cases": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != REGISTRY_SCHEMA or not isinstance(data.get("cases"), list):
        raise ValueError("registry must use ai-ppt-plus/distillation-case-registry/v1")
    return data


def render_pptx(pptx: Path, destination: Path, *, root: Path) -> dict[str, Any]:
    script = Path(__file__).with_name("render_pptx.py")
    report = destination.parent / "pptx-render-report.json"
    command = [sys.executable, str(script), str(pptx), "--output-dir", str(destination), "--report", str(report)]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    if completed.returncode != 0:
        return {"status": "failed", "returncode": completed.returncode, "stderr": completed.stderr[-2000:]}
    pages = [path for path in sorted(destination.glob("*.png")) if path.is_file()]
    return {
        "status": "complete",
        "report": ref(report, role="pptx-render-report", root=root) if report.is_file() else None,
        "references": [ref(page, role="rendered-reference", root=root, source_name=page.name) for page in pages],
    }


def copy_evidence(path_value: str, *, case_root: Path, output: Path, role: str) -> dict[str, Any]:
    """Copy score/report evidence into the immutable case bundle."""
    source = Path(path_value).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    destination = case_root / "evidence" / f"{sha256(source)[:16]}-{safe_name(source.name)}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_copy(source, destination)
    return ref(destination, role=role, root=output, source_name=source.name)


def score_summary(score_ref: dict[str, Any] | None, *, root: Path) -> dict[str, Any]:
    if not score_ref:
        return {}
    path = (root / score_ref["path"]).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        key: data[key]
        for key in ("weighted_score", "technical_valid", "blocker_count", "metrics", "status")
        if key in data
    }


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    registry_path = Path(args.registry).resolve() if args.registry else output / "registry.json"
    sources = [Path(value).resolve() for value in args.source]
    if not sources:
        raise ValueError("at least one --source is required")
    for source in sources:
        if not source.is_file():
            raise FileNotFoundError(source)
        if source.suffix.lower() not in IMAGE_SUFFIXES | {".pptx"}:
            raise ValueError(f"unsupported source type: {source.name}")
    case_id = args.case_id or f"case-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{sha256(sources[0])[:10]}"
    case_root = output / case_id
    case_root.mkdir(parents=True, exist_ok=True)
    case_inputs = case_root / "inputs"
    case_inputs.mkdir(parents=True, exist_ok=True)
    source_refs: list[dict[str, Any]] = []
    target_refs: list[dict[str, Any]] = []
    rendered_refs: list[dict[str, Any]] = []
    render_reports: list[dict[str, Any]] = []
    for source in sources:
        destination = case_inputs / f"{sha256(source)[:16]}-{safe_name(source.name)}"
        atomic_copy(source, destination)
        copied = ref(destination, role="source", root=output, source_name=source.name)
        source_refs.append(copied)
        if source.suffix.lower() == ".pptx":
            target_refs.append({**copied, "role": "canonical-target-pptx"})
            if args.skip_render:
                render_reports.append({"status": "skipped", "reason": "--skip-render", "source": copied})
            else:
                result = render_pptx(destination, case_root / "rendered-pptx", root=output)
                render_reports.append({"status": result.get("status"), "source": copied, "report": result.get("report"), "error": result.get("error"), "stderr": result.get("stderr")})
                rendered_refs.extend(result.get("references") or [])
    candidate_refs: list[dict[str, Any]] = []
    if args.candidate:
        candidate = Path(args.candidate).resolve()
        if not candidate.is_file() or candidate.suffix.lower() != ".pptx":
            raise ValueError("--candidate must be an existing .pptx")
        destination = case_root / "candidates" / f"{sha256(candidate)[:16]}-{safe_name(candidate.name)}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_copy(candidate, destination)
        candidate_id = f"candidate-{sha256(destination)[:12]}"
        score_ref = copy_evidence(args.candidate_score, case_root=case_root, output=output, role="candidate-score") if args.candidate_score else None
        report_refs = [copy_evidence(value, case_root=case_root, output=output, role="candidate-report") for value in args.candidate_report]
        evidence_ready = bool(score_ref or report_refs)
        candidate_refs.append({
            "candidate_id": candidate_id,
            "deck": ref(destination, role="candidate-deck", root=output, source_name=candidate.name),
            "profile": args.profile,
            "status": "awaiting-human-approval" if evidence_ready else "awaiting-evidence",
            "training_eligible": False,
            "score": score_ref,
            "reports": report_refs,
            "score_summary": score_summary(score_ref, root=output),
            "evidence_status": "attached" if evidence_ready else "missing",
        })
    else:
        if args.candidate_score or args.candidate_report:
            raise ValueError("--candidate-score/--candidate-report require --candidate")
        candidate_refs.append({"candidate_id": "awaiting-reconstruction", "status": "awaiting-reconstruction", "training_eligible": False})
    mode = "paired" if any(item["path"].lower().endswith(".pptx") for item in source_refs) and any(Path(item["path"]).suffix.lower() in IMAGE_SUFFIXES for item in source_refs) else ("pptx" if target_refs else "image")
    now = datetime.now(timezone.utc).isoformat()
    intake = {
        "schema": INTAKE_SCHEMA,
        "version": 1,
        "case_id": case_id,
        "created_at": now,
        "input_mode": mode,
        "source_references": source_refs,
        "canonical_target_references": target_refs,
        "rendered_reference_references": rendered_refs,
        "render_status": render_reports,
        "candidate_status": "candidate-ready" if args.candidate else "awaiting-reconstruction",
        "human_approval_required": True,
        "training_eligible": False,
        "next_action": "run image-to-editable-pptx reconstruction, then attach candidate and QA evidence" if not args.candidate else "obtain explicit human approval after reviewing the attached score and reports" if candidate_refs[0].get("evidence_status") == "attached" else "run QA gates and attach a fresh score/report before human approval",
    }
    intake_path = case_root / "intake.json"
    atomic_write_json(intake_path, intake)
    registry = load_registry(registry_path)
    registry["updated_at"] = now
    registry["cases"] = [case for case in registry["cases"] if not (isinstance(case, dict) and case.get("case_id") == case_id)]
    registry["cases"].append({
        "case_id": case_id,
        "created_at": now,
        "input_mode": mode,
        "source_references": source_refs + rendered_refs,
        "intake": ref(intake_path, role="case-intake", root=registry_path.parent),
        "candidates": candidate_refs,
        "learning_status": "human-review-pending",
        "training_eligible": False,
    })
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(registry_path, registry)
    return {"intake": intake, "intake_path": str(intake_path), "registry_path": str(registry_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True, help="PNG/JPG/WebP image or PPTX; repeat for multiple pages")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--registry")
    parser.add_argument("--case-id")
    parser.add_argument("--candidate", help="optional editable PPTX produced by reconstruction")
    parser.add_argument("--candidate-score", help="optional fresh distillation-score.json to copy into the case")
    parser.add_argument("--candidate-report", action="append", default=[], help="optional QA report to copy into the case; repeatable")
    parser.add_argument("--profile", help="candidate repair/reconstruction profile")
    parser.add_argument("--skip-render", action="store_true", help="do not render PPTX sources; intended for controlled/offline tests")
    args = parser.parse_args()
    try:
        result = prepare(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
