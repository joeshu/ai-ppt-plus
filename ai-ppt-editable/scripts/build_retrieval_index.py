#!/usr/bin/env python3
"""Build a dependency-free CPU retrieval index and held-out leakage report.

The index is an auditable baseline for approved reconstruction cases.  It uses
stable source hashes and structured metadata, not a semantic vision encoder;
therefore it improves exact/case-family reuse without pretending to train
model weights.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json


INDEX_SCHEMA = "ai-ppt-plus/distillation-retrieval-index/v1"
EVAL_SCHEMA = "ai-ppt-plus/distillation-retrieval-evaluation/v1"
DATASET_SCHEMA = "ai-ppt-plus/distillation-training-dataset/v1"


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


def read_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"record {line_number} must be a JSON object")
        if not value.get("example_id") or value.get("split") not in {"train", "validation", "test"}:
            raise ValueError(f"record {line_number} has invalid example_id or split")
        if not isinstance(value.get("source"), list) or not value["source"]:
            raise ValueError(f"record {line_number} has no source references")
        records.append(value)
    return records


def source_hashes(record: dict[str, Any]) -> list[str]:
    values = []
    for item in record.get("source") or []:
        if isinstance(item, dict) and isinstance(item.get("sha256"), str) and item["sha256"]:
            values.append(item["sha256"])
    return sorted(set(values))


def build_index(records: list[dict[str, Any]], *, manifest_path: Path, dataset_manifest: dict[str, Any]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    by_source: dict[str, list[str]] = {}
    for record in sorted(records, key=lambda item: str(item["example_id"])):
        hashes = source_hashes(record)
        entry = {
            "example_id": record["example_id"],
            "split": record["split"],
            "task": record.get("task"),
            "profile": (record.get("supervision") or {}).get("profile"),
            "source_sha256": hashes,
            "retrieval_keys": sorted(set(hashes + [str(record.get("task") or ""), str((record.get("supervision") or {}).get("profile") or "")])),
            "target": record.get("target"),
            "metrics": (record.get("supervision") or {}).get("metrics", {}),
        }
        entries.append(entry)
        for value in hashes:
            by_source.setdefault(value, []).append(str(record["example_id"]))
    return {
        "schema": INDEX_SCHEMA,
        "index_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_manifest": {"path": str(manifest_path), "sha256": sha256(manifest_path)},
        "records_sha256": dataset_manifest.get("records_sha256"),
        "entry_count": len(entries),
        "entries": entries,
        "source_lookup": {key: sorted(value) for key, value in sorted(by_source.items())},
        "retrieval_mode": "exact-source-hash-and-structured-metadata",
        "semantic_embedding": False,
        "trainable_weights": False,
        "cpu_only": True,
    }


def evaluate(records: list[dict[str, Any]], *, index_path: Path, manifest_path: Path) -> dict[str, Any]:
    split_hashes: dict[str, set[str]] = {"train": set(), "validation": set(), "test": set()}
    split_counts = {split: 0 for split in split_hashes}
    for record in records:
        split = record["split"]
        split_counts[split] += 1
        split_hashes[split].update(source_hashes(record))
    overlaps: list[dict[str, Any]] = []
    splits = tuple(split_hashes)
    for left_index, left in enumerate(splits):
        for right in splits[left_index + 1:]:
            overlap = sorted(split_hashes[left] & split_hashes[right])
            if overlap:
                overlaps.append({"left": left, "right": right, "source_sha256": overlap})
    holdout_count = split_counts["validation"] + split_counts["test"]
    issues: list[dict[str, Any]] = []
    if not holdout_count:
        issues.append({"code": "insufficient_holdout", "message": "No validation or test records are available for a meaningful held-out evaluation."})
    if overlaps:
        issues.append({"code": "source_leakage", "groups": overlaps})
    return {
        "schema": EVAL_SCHEMA,
        "evaluation_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "index": str(index_path),
        "dataset_manifest": str(manifest_path),
        "valid": not overlaps,
        "status": "passed" if not overlaps and holdout_count else "insufficient-holdout" if not overlaps else "blocked",
        "split_counts": split_counts,
        "holdout_count": holdout_count,
        "source_hash_counts": {split: len(values) for split, values in split_hashes.items()},
        "overlaps": overlaps,
        "issues": issues,
        "cpu_only": True,
        "semantic_quality": "not_measured_without_embedding_model",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--evaluation", required=True)
    parser.add_argument("--require-holdout", action="store_true")
    args = parser.parse_args()
    try:
        records_path = Path(args.records).resolve()
        manifest_path = Path(args.manifest).resolve()
        index_path = Path(args.index).resolve()
        evaluation_path = Path(args.evaluation).resolve()
        dataset_manifest = read_json(manifest_path)
        if dataset_manifest.get("schema") != DATASET_SCHEMA or dataset_manifest.get("retrieval_ready") is not True:
            raise ValueError("dataset manifest must be retrieval-ready")
        expected_records_sha256 = dataset_manifest.get("records_sha256")
        if not isinstance(expected_records_sha256, str) or expected_records_sha256 != sha256(records_path):
            raise ValueError("records hash does not match the retrieval-ready dataset manifest")
        records = read_records(records_path)
        index = build_index(records, manifest_path=manifest_path, dataset_manifest=dataset_manifest)
        atomic_write_json(index_path, index)
        evaluation = evaluate(records, index_path=index_path, manifest_path=manifest_path)
        atomic_write_json(evaluation_path, evaluation)
        blocked = evaluation["status"] == "blocked" or (args.require_holdout and evaluation["status"] != "passed")
        print(json.dumps({"schema": INDEX_SCHEMA, "valid": not blocked, "index": str(index_path), "evaluation": str(evaluation_path), "entry_count": index["entry_count"], "evaluation_status": evaluation["status"]}, ensure_ascii=False))
        return 2 if blocked else 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": INDEX_SCHEMA, "valid": False, "status": "blocked", "code": "retrieval_index_failed", "message": str(exc)}, ensure_ascii=False))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
