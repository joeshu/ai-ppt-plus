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
EXPECTED_ENTRIES = {
    "ai-ppt-plus": ("orchestrator", "SKILL.md", "agents/openai.yaml"),
    "ai-ppt-visual-gen": ("visual-worker", "ai-ppt-visual-gen/SKILL.md", "ai-ppt-visual-gen/agents/openai.yaml"),
    "ai-ppt-editable": ("editable-worker", "ai-ppt-editable/SKILL.md", "ai-ppt-editable/agents/openai.yaml"),
}


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

    entries = package.get("skill_entries")
    if not isinstance(entries, list):
        entries = []
        issues.append({"severity": "blocker", "code": "skill_entries_missing"})
    by_name: dict[str, dict] = {}
    seen_paths: set[str] = set()
    seen_roles: set[str] = set()
    for index, item in enumerate(entries):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            issues.append({"severity": "blocker", "code": "skill_entry_invalid", "index": index})
            continue
        name = item["name"]
        if name in by_name:
            issues.append({"severity": "blocker", "code": "skill_entry_duplicate_name", "name": name})
        by_name[name] = item
        for field in ("entrypoint", "agent"):
            value = item.get(field)
            if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
                issues.append({"severity": "blocker", "code": "skill_entry_path_invalid", "name": name, "field": field, "path": value})
            elif field == "entrypoint":
                if value in seen_paths:
                    issues.append({"severity": "blocker", "code": "skill_entry_duplicate_path", "path": value})
                seen_paths.add(value)
        role = item.get("role")
        if not isinstance(role, str) or role in seen_roles:
            issues.append({"severity": "blocker", "code": "skill_entry_role_invalid", "name": name, "role": role})
        elif role:
            seen_roles.add(role)
    if set(by_name) != set(EXPECTED_ENTRIES):
        issues.append({"severity": "blocker", "code": "skill_entry_set_invalid", "expected": sorted(EXPECTED_ENTRIES), "observed": sorted(by_name)})
    for name, (role, relative, agent_relative) in EXPECTED_ENTRIES.items():
        item = by_name.get(name)
        if not isinstance(item, dict):
            continue
        expected = {"role": role, "entrypoint": relative, "agent": agent_relative}
        for field, value in expected.items():
            if item.get(field) != value:
                issues.append({"severity": "blocker", "code": "skill_entry_contract_mismatch", "name": name, "field": field, "expected": value, "observed": item.get(field)})
        entrypoint = root / relative
        if not entrypoint.is_file():
            issues.append({"severity": "blocker", "code": "entrypoint_missing", "name": name, "path": str(entrypoint)})
            continue
        text = entrypoint.read_text(encoding="utf-8")
        declared_name = NAME_RE.search(text)
        if not declared_name or declared_name.group(1) != name:
            issues.append({"severity": "blocker", "code": "entrypoint_name_mismatch", "expected": name, "path": relative})
        declared_revision = REVISION_RE.search(text)
        if not declared_revision or declared_revision.group(1) != revision:
            issues.append({"severity": "blocker", "code": "entrypoint_revision_mismatch", "name": name, "expected": revision, "observed": declared_revision.group(1) if declared_revision else None})
        if not (root / agent_relative).is_file():
            issues.append({"severity": "blocker", "code": "skill_agent_missing", "name": name, "path": agent_relative})

    shared_runtime = package.get("shared_runtime")
    if not isinstance(shared_runtime, dict) or shared_runtime.get("policy") != "single-source":
        issues.append({"severity": "blocker", "code": "shared_runtime_policy_invalid", "observed": shared_runtime})
    else:
        roots = shared_runtime.get("roots")
        if roots != ["scripts", "assets", "references"]:
            issues.append({"severity": "blocker", "code": "shared_runtime_roots_invalid", "expected": ["scripts", "assets", "references"], "observed": roots})

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
