#!/usr/bin/env python3
"""Detect drift between the canonical runtime and self-contained workers.

The root package is the checked-in source of truth for shared runtime files.
This gate compares every worker file covered by its policy globs and also
requires a small set of critical files to exist in both locations. It never
modifies either package.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
from pathlib import Path

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/runtime-mirror-validation/v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def excluded(relative: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(relative, pattern) for pattern in patterns)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--worker", action="append", help="worker directory, relative to --root; may be repeated")
    parser.add_argument("--policy", help="mirror policy JSON; defaults to assets/runtime-mirror-policy.json")
    parser.add_argument("--report")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    policy_path = Path(args.policy).resolve() if args.policy else root / "assets" / "runtime-mirror-policy.json"
    issues: list[dict] = []
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception as exc:
        policy = {}
        issues.append({"severity": "blocker", "code": "mirror_policy_unreadable", "message": f"{type(exc).__name__}: {exc}"})
    if not isinstance(policy, dict) or policy.get("schema") != "ai-ppt-plus/runtime-mirror/v1":
        issues.append({"severity": "blocker", "code": "mirror_policy_schema_invalid", "observed": policy.get("schema") if isinstance(policy, dict) else None})
    pairs = policy.get("pairs") if isinstance(policy, dict) and isinstance(policy.get("pairs"), list) else []
    selected = set(args.worker or [])
    pair_results = []
    for pair in pairs:
        if not isinstance(pair, dict):
            issues.append({"severity": "blocker", "code": "mirror_pair_invalid"})
            continue
        worker_name = pair.get("worker")
        if selected and worker_name not in selected:
            continue
        worker = root / str(worker_name)
        globs = [item for item in pair.get("compare_globs", []) if isinstance(item, str)]
        excludes = [item for item in pair.get("exclude", []) if isinstance(item, str)]
        adapter_exclusions = pair.get("adapter_exclusions", [])
        adapter_reasons: dict[str, str] = {}
        if adapter_exclusions is None:
            adapter_exclusions = []
        if not isinstance(adapter_exclusions, list):
            issues.append({"severity": "blocker", "code": "mirror_adapter_exclusions_invalid", "worker": worker_name})
            adapter_exclusions = []
        for index, item in enumerate(adapter_exclusions):
            if not isinstance(item, dict):
                issues.append({"severity": "blocker", "code": "mirror_adapter_exclusion_invalid", "worker": worker_name, "index": index})
                continue
            path = item.get("path")
            reason = item.get("reason")
            if not isinstance(path, str) or not path.strip() or not isinstance(reason, str) or not reason.strip():
                issues.append({"severity": "blocker", "code": "mirror_adapter_exclusion_evidence_missing", "worker": worker_name, "index": index})
                continue
            if path in adapter_reasons or path in excludes:
                issues.append({"severity": "blocker", "code": "mirror_adapter_exclusion_duplicate", "worker": worker_name, "path": path})
                continue
            adapter_reasons[path] = reason
        excludes = list(dict.fromkeys(excludes + list(adapter_reasons)))
        required = [item for item in pair.get("required_paths", []) if isinstance(item, str)]
        compared = 0
        pair_issues = []
        for relative, reason in adapter_reasons.items():
            adapter_path = worker / relative
            if not adapter_path.is_file():
                issue = {"severity": "blocker", "code": "mirror_adapter_worker_missing", "worker": worker_name, "path": relative, "reason": reason}
                issues.append(issue)
                pair_issues.append(issue)

        candidates: set[Path] = set()
        for pattern in globs:
            candidates.update(path for path in worker.glob(pattern) if path.is_file())
        for worker_path in sorted(candidates):
            relative = worker_path.relative_to(worker).as_posix()
            if excluded(relative, excludes):
                continue
            source_path = root / relative
            compared += 1
            if not source_path.is_file():
                issue = {"severity": "blocker", "code": "mirror_source_missing", "worker": worker_name, "path": relative}
                issues.append(issue)
                pair_issues.append(issue)
                continue
            expected = sha256(source_path)
            observed = sha256(worker_path)
            if expected != observed:
                issue = {"severity": "blocker", "code": "mirror_hash_mismatch", "worker": worker_name, "path": relative, "source_sha256": expected, "worker_sha256": observed}
                issues.append(issue)
                pair_issues.append(issue)

        for relative in required:
            source_path = root / relative
            worker_path = worker / relative
            if not source_path.is_file():
                issue = {"severity": "blocker", "code": "mirror_required_source_missing", "worker": worker_name, "path": relative}
                issues.append(issue)
                pair_issues.append(issue)
            elif not worker_path.is_file():
                issue = {"severity": "blocker", "code": "mirror_required_worker_missing", "worker": worker_name, "path": relative}
                issues.append(issue)
                pair_issues.append(issue)
            elif sha256(source_path) != sha256(worker_path) and not excluded(relative, excludes):
                issue = {"severity": "blocker", "code": "mirror_required_hash_mismatch", "worker": worker_name, "path": relative}
                issues.append(issue)
                pair_issues.append(issue)
        if not worker.is_dir():
            issue = {"severity": "blocker", "code": "mirror_worker_missing", "worker": worker_name, "path": str(worker)}
            issues.append(issue)
            pair_issues.append(issue)
        pair_results.append({"worker": worker_name, "compared_files": compared, "adapter_exclusions": [{"path": path, "reason": reason} for path, reason in adapter_reasons.items()], "issues": pair_issues})

    if not pairs:
        issues.append({"severity": "blocker", "code": "mirror_policy_pairs_missing"})
    result = {
        "schema": SCHEMA,
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "root": str(root),
        "policy": str(policy_path),
        "pairs": pair_results,
        "issues": issues,
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
