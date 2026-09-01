#!/usr/bin/env python3
"""Approve cases and export hash-bound distillation training records.

The exporter is deliberately strict: machine-passed candidates are not
training data until a human explicitly confirms visual fidelity, formal text,
and editability.  It can emit a portable JSONL manifest and optionally copy
all referenced artifacts into a content-addressed directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atomic_output import atomic_copy, atomic_write_json, atomic_write_text


REGISTRY_SCHEMA = "ai-ppt-plus/distillation-case-registry/v1"
APPROVAL_SCHEMA = "ai-ppt-plus/distillation-human-approval/v1"
DATASET_SCHEMA = "ai-ppt-plus/distillation-training-dataset/v1"
EXAMPLE_SCHEMA = "ai-ppt-plus/distillation-training-example/v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def read_registry(path: Path) -> dict[str, Any]:
    data = read_json(path)
    if data.get("schema") != REGISTRY_SCHEMA or not isinstance(data.get("cases"), list):
        raise ValueError("registry must use ai-ppt-plus/distillation-case-registry/v1")
    return data


def validate_ref(ref: Any, *, role: str, issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        issues.append({"code": "artifact_ref_invalid", "role": role})
        return None
    path_value = ref.get("path")
    expected = ref.get("sha256")
    if not isinstance(path_value, str) or not path_value.strip():
        issues.append({"code": "artifact_path_missing", "role": role})
        return None
    path = Path(path_value).resolve()
    if not path.is_file():
        issues.append({"code": "artifact_missing", "role": role, "path": str(path)})
        return None
    observed = sha256(path)
    if not isinstance(expected, str) or expected != observed:
        issues.append({"code": "artifact_hash_mismatch", "role": role, "path": str(path), "expected": observed, "observed": expected})
        return None
    result = {"role": role, "path": str(path), "sha256": observed}
    if "slide" in ref:
        result["slide"] = ref["slide"]
    return result


def approval_record(args: argparse.Namespace) -> dict[str, Any]:
    registry_path = Path(args.registry).resolve()
    registry = read_registry(registry_path)
    if args.human_confirmed is not True:
        raise ValueError("--human-confirmed is required; automation cannot infer human approval")
    if not args.approved_by.strip() or not args.approval_note.strip():
        raise ValueError("--approved-by and --approval-note are required")
    found_case = None
    found_candidate = None
    for case in registry["cases"]:
        if not isinstance(case, dict) or case.get("case_id") != args.case_id:
            continue
        found_case = case
        for candidate in case.get("candidates") or []:
            if isinstance(candidate, dict) and candidate.get("candidate_id") == args.candidate_id:
                found_candidate = candidate
                break
    if found_case is None or found_candidate is None:
        raise ValueError("case or candidate not found")
    score_ref = found_candidate.get("score")
    issues: list[dict[str, Any]] = []
    checked_score_ref = validate_ref(score_ref, role="candidate-score", issues=issues)
    if issues or checked_score_ref is None:
        raise ValueError(f"candidate score is not fresh: {issues}")
    score = read_json(Path(checked_score_ref["path"]))
    if score.get("technical_valid") is not True or int(score.get("blocker_count", 0) or 0) != 0:
        raise ValueError("only technically valid, blocker-free candidates may be approved for training")
    now = datetime.now(timezone.utc).isoformat()
    found_candidate["human_approval"] = {
        "schema": APPROVAL_SCHEMA,
        "human_confirmed": True,
        "approved_by": args.approved_by.strip(),
        "approval_note": args.approval_note.strip(),
        "approved_at": now,
        "reviewed_dimensions": ["visual_fidelity", "formal_content", "editability"],
    }
    found_candidate["status"] = "human-approved"
    found_candidate["training_eligible"] = True
    found_case["learning_status"] = "human-approved"
    result = {**registry, "updated_at": now}
    atomic_write_json(registry_path, result)
    return result


def split_for(case_id: str, seed: str) -> str:
    value = int(hashlib.sha256(f"{seed}|{case_id}".encode("utf-8")).hexdigest()[:8], 16) % 100
    if value < 80:
        return "train"
    if value < 90:
        return "validation"
    return "test"


def materialize(ref: dict[str, Any], *, root: Path, dataset_root: Path) -> dict[str, Any]:
    source = Path(ref["path"])
    destination = root / ref["sha256"][:16] / f"{ref['role']}{source.suffix.lower()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and sha256(destination) != ref["sha256"]:
        raise ValueError(f"materialized artifact hash collision: {destination}")
    if not destination.is_file():
        atomic_copy(source, destination)
    relative = os.path.relpath(destination, dataset_root).replace(os.sep, "/")
    return {**ref, "path": relative, "materialized": True}


def export_dataset(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    registry_path = Path(args.registry).resolve()
    registry = read_registry(registry_path)
    output_path = Path(args.output).resolve()
    manifest_path = Path(args.manifest).resolve()
    materialize_root = Path(args.materialize_dir).resolve() if args.materialize_dir else None
    eligible: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    rejected: list[dict[str, Any]] = []
    for case in registry["cases"]:
        if not isinstance(case, dict):
            rejected.append({"code": "case_invalid"})
            continue
        candidates = []
        for candidate in case.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("training_eligible") is not True or candidate.get("status") != "human-approved":
                continue
            approval = candidate.get("human_approval")
            if not isinstance(approval, dict) or approval.get("human_confirmed") is not True or not approval.get("approved_by") or not approval.get("approval_note"):
                rejected.append({"case_id": case.get("case_id"), "candidate_id": candidate.get("candidate_id"), "code": "human_approval_incomplete"})
                continue
            score_summary = candidate.get("score_summary") if isinstance(candidate.get("score_summary"), dict) else {}
            score_value = float(score_summary.get("weighted_score") or 0.0)
            candidates.append((score_value, candidate, case))
        if candidates:
            candidates.sort(key=lambda item: (-item[0], str(item[1].get("candidate_id"))))
            eligible.append(candidates[0])
    seen_sources: set[tuple[str, ...]] = set()
    records: list[dict[str, Any]] = []
    for _, candidate, case in sorted(eligible, key=lambda item: str(case.get("case_id"))):
        case_id = str(case.get("case_id"))
        candidate_id = str(candidate.get("candidate_id"))
        issues: list[dict[str, Any]] = []
        sources = [validate_ref(ref, role="source", issues=issues) for ref in case.get("source_references") or []]
        sources = [ref for ref in sources if ref is not None]
        deck = validate_ref(candidate.get("deck"), role="candidate-deck", issues=issues)
        score_ref = validate_ref(candidate.get("score"), role="candidate-score", issues=issues)
        reports = [validate_ref(ref, role="report", issues=issues) for ref in candidate.get("reports") or []]
        reports = [ref for ref in reports if ref is not None]
        if not sources:
            issues.append({"code": "source_references_missing"})
        source_key = tuple(sorted(ref["sha256"] for ref in sources))
        if source_key in seen_sources:
            issues.append({"code": "duplicate_source_group"})
        score_data = read_json(Path(score_ref["path"])) if score_ref else {}
        if score_data.get("technical_valid") is not True or int(score_data.get("blocker_count", 0) or 0) != 0:
            issues.append({"code": "score_not_blocker_free"})
        if issues:
            rejected.append({"case_id": case_id, "candidate_id": candidate_id, "code": "candidate_not_exportable", "issues": issues})
            continue
        seen_sources.add(source_key)
        if materialize_root:
            source_records = [materialize(ref, root=materialize_root, dataset_root=output_path.parent) for ref in sources]
            deck_record = materialize(deck, root=materialize_root, dataset_root=output_path.parent)
            score_record = materialize(score_ref, root=materialize_root, dataset_root=output_path.parent)
            report_records = [materialize(ref, root=materialize_root, dataset_root=output_path.parent) for ref in reports]
        else:
            source_records, deck_record, score_record, report_records = sources, deck, score_ref, reports
        records.append({
            "schema": EXAMPLE_SCHEMA,
            "example_id": f"{case_id}:{candidate_id}",
            "task": "reconstruct-reference-image-to-editable-pptx",
            "split": split_for(case_id, args.split_seed),
            "source": source_records,
            "target": {"deck": deck_record},
            "supervision": {"score": score_record, "reports": report_records, "profile": candidate.get("profile"), "metrics": candidate.get("score_summary", {}).get("metrics", {})},
            "provenance": {"case_id": case_id, "candidate_id": candidate_id, "human_approval": candidate["human_approval"], "source_sha256": list(source_key)},
        })
    lines = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    atomic_write_text(output_path, lines)
    manifest = {
        "schema": DATASET_SCHEMA,
        "dataset_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry": {"path": str(registry_path), "sha256": sha256(registry_path)},
        "records_path": str(output_path),
        "records_sha256": sha256(output_path),
        "record_count": len(records),
        "splits": {split: sum(1 for item in records if item["split"] == split) for split in ("train", "validation", "test")},
        "rejected_count": len(rejected),
        "rejected": rejected,
        "dedupe_policy": "one highest-scoring human-approved candidate per source hash group",
        "self_contained": bool(materialize_root) and all(all("materialized" in ref for ref in item["source"]) and item["target"]["deck"].get("materialized") is True for item in records),
        "retrieval_ready": bool(records) and not rejected,
        "supervised_training_ready": False,
        "supervised_training_note": "Use this approved, hash-bound JSONL as source data; a model-specific adapter must still convert manifests and PPTX targets into tensors or structured labels.",
        "human_review_required": False,
        "approval_policy": "Only explicit human_confirmed approvals with fresh source, deck, score, and report hashes are exported.",
    }
    atomic_write_json(manifest_path, manifest)
    return manifest, 0 if records and not rejected else 2


def main() -> int:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    approve = sub.add_parser("approve-case")
    approve.add_argument("--registry", required=True)
    approve.add_argument("--case-id", required=True)
    approve.add_argument("--candidate-id", required=True)
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--approval-note", required=True)
    approve.add_argument("--human-confirmed", action="store_true", required=True)
    export = sub.add_parser("export")
    export.add_argument("--registry", required=True)
    export.add_argument("--output", required=True)
    export.add_argument("--manifest", required=True)
    export.add_argument("--materialize-dir")
    export.add_argument("--split-seed", default="ai-ppt-editable-v1")
    args = root.parse_args()
    try:
        if args.command == "approve-case":
            result = approval_record(args)
            print(json.dumps({"schema": REGISTRY_SCHEMA, "valid": True, "registry": str(Path(args.registry).resolve()), "case_id": args.case_id, "candidate_id": args.candidate_id, "training_eligible": True}, ensure_ascii=False))
            return 0
        manifest, code = export_dataset(args)
        print(json.dumps({"schema": DATASET_SCHEMA, "valid": code == 0, "manifest": str(Path(args.manifest).resolve()), "record_count": manifest["record_count"], "rejected_count": manifest["rejected_count"], "retrieval_ready": manifest["retrieval_ready"]}, ensure_ascii=False))
        return code
    except (OSError, ValueError, json.JSONDecodeError, shutil.Error) as exc:
        print(json.dumps({"schema": DATASET_SCHEMA, "valid": False, "status": "blocked", "code": "training_export_failed", "message": str(exc)}, ensure_ascii=False))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
