#!/usr/bin/env python3
"""Validate that the editable worker still matches the pinned perfect source."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

from atomic_output import atomic_write_json


COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
SCHEMA = "ai-ppt-editable/upstream-perfect-sync/v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return None
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root_default = Path(__file__).resolve().parents[1]
    parser.add_argument("--skill-dir", default=str(root_default))
    parser.add_argument("--manifest", default="")
    parser.add_argument("--source-dir", help="optional perfect-branch checkout for source-side verification")
    parser.add_argument("--require-source", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()

    root = Path(args.skill_dir).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else root / "assets" / "upstream-perfect-sync.json"
    issues: list[dict] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        manifest = {}
        issues.append({"severity": "blocker", "code": "manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"})

    if manifest.get("schema") != SCHEMA:
        issues.append({"severity": "blocker", "code": "manifest_schema_invalid", "observed": manifest.get("schema")})
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    commit = source.get("commit")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        issues.append({"severity": "blocker", "code": "source_commit_invalid", "observed": commit})
    if source.get("repository") != "joeshu/ai-ppt-plus" or source.get("ref") != "完美第一版":
        issues.append({"severity": "blocker", "code": "source_identity_invalid", "observed": source})

    entries = manifest.get("synced_files")
    if not isinstance(entries, list) or not entries:
        entries = []
        issues.append({"severity": "blocker", "code": "synced_files_missing"})
    seen_source: set[str] = set()
    seen_target: set[str] = set()
    observed_files: list[dict] = []
    source_root = Path(args.source_dir).resolve() if args.source_dir else None
    if args.require_source and source_root is None:
        issues.append({"severity": "blocker", "code": "source_checkout_required"})

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            issues.append({"severity": "blocker", "code": "sync_entry_invalid", "index": index})
            continue
        source_relative = safe_relative(entry.get("source_path"))
        target_relative = safe_relative(entry.get("target_path"))
        expected = entry.get("sha256")
        if source_relative is None or target_relative is None:
            issues.append({"severity": "blocker", "code": "sync_path_invalid", "index": index})
            continue
        if source_relative in seen_source or target_relative in seen_target:
            issues.append({"severity": "blocker", "code": "sync_path_duplicate", "index": index, "source_path": source_relative, "target_path": target_relative})
        seen_source.add(source_relative)
        seen_target.add(target_relative)
        if not isinstance(expected, str) or not HASH_RE.fullmatch(expected):
            issues.append({"severity": "blocker", "code": "sync_hash_invalid", "path": target_relative})
            continue
        target_path = root / target_relative
        record = {"source_path": source_relative, "target_path": target_relative, "expected_sha256": expected}
        if not target_path.is_file():
            issues.append({"severity": "blocker", "code": "target_file_missing", "path": target_relative})
            observed_files.append(record)
            continue
        observed = sha256(target_path)
        record["observed_sha256"] = observed
        if observed != expected:
            issues.append({"severity": "blocker", "code": "target_hash_mismatch", "path": target_relative, "expected": expected, "observed": observed})
        expected_executable = entry.get("executable")
        if isinstance(expected_executable, bool) and os.access(target_path, os.X_OK) != expected_executable:
            issues.append({"severity": "blocker", "code": "target_mode_mismatch", "path": target_relative, "expected_executable": expected_executable, "observed_executable": os.access(target_path, os.X_OK)})
        if source_root is not None:
            source_path = source_root / source_relative
            if not source_path.is_file():
                issues.append({"severity": "blocker", "code": "source_file_missing", "path": source_relative})
            elif sha256(source_path) != expected:
                issues.append({"severity": "blocker", "code": "source_hash_mismatch", "path": source_relative, "expected": expected, "observed": sha256(source_path)})
        observed_files.append(record)

    result = {
        "schema": "ai-ppt-editable/upstream-perfect-sync-validation/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "manifest": str(manifest_path),
        "source": source,
        "synced_file_count": len(entries),
        "observed_files": observed_files,
        "excluded_paths": manifest.get("excluded_paths", []),
        "issues": issues,
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
