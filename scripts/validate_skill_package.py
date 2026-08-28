#!/usr/bin/env python3
"""Validate the checked-in skill package and optional runtime copy.

The repository is the source of truth.  When ``--runtime-skill-dir`` is
provided, every managed file is compared by SHA-256 so a stale installed
skill cannot silently execute older routing or release rules.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from atomic_output import atomic_write_json


PACKAGE_SCHEMA = "ai-ppt-plus/skill-package/v1"
NAME_RE = re.compile(r"^name:\s*([a-z0-9][a-z0-9-]*)\s*$", re.MULTILINE)
REVISION_RE = re.compile(r"^\s*package_revision:\s*([^\s#]+)\s*$", re.MULTILINE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-dir", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--runtime-skill-dir")
    parser.add_argument("--report")
    args = parser.parse_args()

    root = Path(args.skill_dir).resolve()
    issues: list[dict] = []
    manifest_path = root / "assets" / "skill-package.json"
    try:
        package = load_json(manifest_path)
    except Exception as exc:
        package = {}
        issues.append({"severity": "blocker", "code": "package_manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"})

    if package.get("schema") != PACKAGE_SCHEMA:
        issues.append({"severity": "blocker", "code": "package_schema_invalid", "observed": package.get("schema")})
    if package.get("skill") != "ai-ppt-plus":
        issues.append({"severity": "blocker", "code": "package_skill_invalid", "observed": package.get("skill")})
    revision = package.get("package_revision")
    if not isinstance(revision, str) or not revision.strip():
        issues.append({"severity": "blocker", "code": "package_revision_missing"})

    entrypoint = root / str(package.get("entrypoint") or "SKILL.md")
    entrypoint_text = ""
    if not entrypoint.is_file():
        issues.append({"severity": "blocker", "code": "entrypoint_missing", "path": str(entrypoint)})
    else:
        entrypoint_text = entrypoint.read_text(encoding="utf-8")
        name = NAME_RE.search(entrypoint_text)
        if not name or name.group(1) != "ai-ppt-plus":
            issues.append({"severity": "blocker", "code": "entrypoint_name_mismatch"})
        entrypoint_revision = REVISION_RE.search(entrypoint_text)
        if not entrypoint_revision or entrypoint_revision.group(1) != revision:
            issues.append({"severity": "blocker", "code": "entrypoint_revision_mismatch", "expected": revision, "observed": entrypoint_revision.group(1) if entrypoint_revision else None})

    required_files = package.get("required_files")
    if not isinstance(required_files, list) or not required_files:
        issues.append({"severity": "blocker", "code": "required_files_missing"})
        required_files = []
    managed_globs = package.get("managed_globs")
    if not isinstance(managed_globs, list) or not managed_globs:
        issues.append({"severity": "blocker", "code": "managed_globs_missing"})
        managed_globs = []
    managed_paths = set()
    file_hashes: dict[str, str] = {}
    for relative in required_files:
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            issues.append({"severity": "blocker", "code": "required_file_path_invalid", "path": relative})
            continue
        managed_paths.add(relative)
    for pattern in managed_globs:
        if not isinstance(pattern, str) or not pattern or Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            issues.append({"severity": "blocker", "code": "managed_glob_invalid", "pattern": pattern})
            continue
        matches = [path for path in root.glob(pattern) if path.is_file()]
        if not matches:
            issues.append({"severity": "blocker", "code": "managed_glob_empty", "pattern": pattern})
        for path in matches:
            managed_paths.add(path.relative_to(root).as_posix())
    for relative in sorted(managed_paths):
        path = root / relative
        if not path.is_file():
            issues.append({"severity": "blocker", "code": "managed_file_missing", "path": relative})
        else:
            file_hashes[relative] = sha256(path)

    runtime_evidence = None
    if args.runtime_skill_dir:
        runtime_root = Path(args.runtime_skill_dir).resolve()
        runtime_evidence = {"root": str(runtime_root), "files": [], "missing": [], "mismatches": []}
        for relative, expected_hash in file_hashes.items():
            candidate = runtime_root / relative
            if not candidate.is_file():
                runtime_evidence["missing"].append(relative)
                issues.append({"severity": "blocker", "code": "runtime_file_missing", "path": relative})
                continue
            observed_hash = sha256(candidate)
            runtime_evidence["files"].append({"path": relative, "sha256": observed_hash})
            if observed_hash != expected_hash:
                runtime_evidence["mismatches"].append({"path": relative, "expected": expected_hash, "observed": observed_hash})
                issues.append({"severity": "blocker", "code": "runtime_file_mismatch", "path": relative, "expected": expected_hash, "observed": observed_hash})

    result = {
        "schema": "ai-ppt-plus/skill-package-validation/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "skill": package.get("skill"),
        "package_revision": revision,
        "skill_dir": str(root),
        "required_files": file_hashes,
        "runtime": runtime_evidence,
        "issues": issues,
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
