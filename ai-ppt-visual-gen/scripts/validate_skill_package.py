#!/usr/bin/env python3
"""Validate one self-contained skill package and optional bundled children."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from atomic_output import atomic_write_json


PACKAGE_SCHEMA = "ai-ppt-plus/skill-package/v2"
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


def safe_relative(value, *, code: str, issues: list[dict]) -> str | None:
    if not isinstance(value, str) or not value:
        issues.append({"severity": "blocker", "code": code, "path": value})
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        issues.append({"severity": "blocker", "code": code, "path": value})
        return None
    return value


def inspect_entrypoint(root: Path, package: dict, issues: list[dict]) -> None:
    skill = package.get("skill")
    revision = package.get("package_revision")
    relative = safe_relative(package.get("entrypoint") or "SKILL.md", code="entrypoint_path_invalid", issues=issues)
    if relative is None:
        return
    path = root / relative
    if not path.is_file():
        issues.append({"severity": "blocker", "code": "entrypoint_missing", "path": str(path)})
        return
    text = path.read_text(encoding="utf-8")
    name = NAME_RE.search(text)
    if not name or name.group(1) != skill:
        issues.append({
            "severity": "blocker",
            "code": "entrypoint_name_mismatch",
            "expected": skill,
            "observed": name.group(1) if name else None,
        })
    declared_revision = REVISION_RE.search(text)
    if not declared_revision or declared_revision.group(1) != revision:
        issues.append({
            "severity": "blocker",
            "code": "entrypoint_revision_mismatch",
            "expected": revision,
            "observed": declared_revision.group(1) if declared_revision else None,
        })


def inspect_self_contained(root: Path, package: dict, issues: list[dict]) -> None:
    contract = package.get("self_contained")
    if not isinstance(contract, dict) or contract.get("policy") != "self-contained":
        issues.append({"severity": "blocker", "code": "self_contained_policy_invalid", "observed": contract})
        return
    required_dirs = contract.get("required_dirs")
    if not isinstance(required_dirs, list) or not required_dirs:
        issues.append({"severity": "blocker", "code": "self_contained_dirs_missing"})
        return
    for value in required_dirs:
        relative = safe_relative(value, code="self_contained_dir_invalid", issues=issues)
        if relative is None:
            continue
        directory = root / relative
        if not directory.is_dir():
            issues.append({"severity": "blocker", "code": "self_contained_dir_missing", "path": relative})
        elif not any(path.is_file() for path in directory.rglob("*")):
            issues.append({"severity": "blocker", "code": "self_contained_dir_empty", "path": relative})


def collect_managed_files(root: Path, package: dict, issues: list[dict]) -> dict[str, str]:
    required_files = package.get("required_files")
    if not isinstance(required_files, list) or not required_files:
        issues.append({"severity": "blocker", "code": "required_files_missing"})
        required_files = []
    managed_globs = package.get("managed_globs")
    if not isinstance(managed_globs, list) or not managed_globs:
        issues.append({"severity": "blocker", "code": "managed_globs_missing"})
        managed_globs = []
    managed_paths: set[str] = set()
    for value in required_files:
        relative = safe_relative(value, code="required_file_path_invalid", issues=issues)
        if relative is not None:
            managed_paths.add(relative)
    for pattern in managed_globs:
        relative = safe_relative(pattern, code="managed_glob_invalid", issues=issues)
        if relative is None:
            continue
        matches = [path for path in root.glob(relative) if path.is_file()]
        if not matches:
            issues.append({"severity": "blocker", "code": "managed_glob_empty", "pattern": relative})
        managed_paths.update(path.relative_to(root).as_posix() for path in matches)
    hashes: dict[str, str] = {}
    for relative in sorted(managed_paths):
        path = root / relative
        if not path.is_file():
            issues.append({"severity": "blocker", "code": "managed_file_missing", "path": relative})
        else:
            hashes[relative] = sha256(path)
    return hashes


def inspect_bundled_skills(root: Path, package: dict, revision, issues: list[dict]) -> list[dict]:
    bundled = package.get("bundled_skills", [])
    if not isinstance(bundled, list):
        issues.append({"severity": "blocker", "code": "bundled_skills_invalid"})
        return []
    evidence = []
    seen_names: set[str] = set()
    seen_roots: set[str] = set()
    for index, item in enumerate(bundled):
        if not isinstance(item, dict):
            issues.append({"severity": "blocker", "code": "bundled_skill_invalid", "index": index})
            continue
        name = item.get("name")
        relative = safe_relative(item.get("root"), code="bundled_skill_root_invalid", issues=issues)
        if not isinstance(name, str) or not name:
            issues.append({"severity": "blocker", "code": "bundled_skill_name_invalid", "index": index})
            continue
        if name in seen_names:
            issues.append({"severity": "blocker", "code": "bundled_skill_duplicate_name", "name": name})
        seen_names.add(name)
        if relative is None:
            continue
        if relative in seen_roots:
            issues.append({"severity": "blocker", "code": "bundled_skill_duplicate_root", "root": relative})
        seen_roots.add(relative)
        child_root = root / relative
        manifest = child_root / "assets" / "skill-package.json"
        child = {}
        try:
            child = load_json(manifest)
        except Exception as exc:
            issues.append({
                "severity": "blocker",
                "code": "bundled_skill_manifest_unreadable",
                "name": name,
                "message": f"{type(exc).__name__}: {exc}",
            })
        if child.get("schema") != PACKAGE_SCHEMA:
            issues.append({"severity": "blocker", "code": "bundled_skill_schema_invalid", "name": name, "observed": child.get("schema")})
        if child.get("skill") != name:
            issues.append({"severity": "blocker", "code": "bundled_skill_name_mismatch", "expected": name, "observed": child.get("skill")})
        if child.get("package_revision") != revision:
            issues.append({"severity": "blocker", "code": "bundled_skill_revision_mismatch", "name": name, "expected": revision, "observed": child.get("package_revision")})
        child_issues: list[dict] = []
        if child:
            inspect_entrypoint(child_root, child, child_issues)
            inspect_self_contained(child_root, child, child_issues)
            collect_managed_files(child_root, child, child_issues)
        for issue in child_issues:
            issues.append({**issue, "bundled_skill": name})
        evidence.append({"name": name, "root": str(child_root), "manifest": str(manifest), "issues": child_issues})
    return evidence


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
    skill = package.get("skill")
    if not isinstance(skill, str) or not skill:
        issues.append({"severity": "blocker", "code": "package_skill_invalid", "observed": skill})
    revision = package.get("package_revision")
    if not isinstance(revision, str) or not revision:
        issues.append({"severity": "blocker", "code": "package_revision_missing"})

    inspect_entrypoint(root, package, issues)
    inspect_self_contained(root, package, issues)
    file_hashes = collect_managed_files(root, package, issues)
    bundled_evidence = inspect_bundled_skills(root, package, revision, issues)

    runtime_evidence = None
    if args.runtime_skill_dir:
        runtime_root = Path(args.runtime_skill_dir).resolve()
        runtime_evidence = {"root": str(runtime_root), "missing": [], "mismatches": []}
        for relative, expected in file_hashes.items():
            candidate = runtime_root / relative
            if not candidate.is_file():
                runtime_evidence["missing"].append(relative)
                issues.append({"severity": "blocker", "code": "runtime_file_missing", "path": relative})
                continue
            observed = sha256(candidate)
            if observed != expected:
                runtime_evidence["mismatches"].append({"path": relative, "expected": expected, "observed": observed})
                issues.append({"severity": "blocker", "code": "runtime_file_mismatch", "path": relative})

    result = {
        "schema": "ai-ppt-plus/skill-package-validation/v2",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "skill": skill,
        "package_revision": revision,
        "skill_dir": str(root),
        "managed_file_count": len(file_hashes),
        "required_files": file_hashes,
        "bundled_skills": bundled_evidence,
        "runtime": runtime_evidence,
        "issues": issues,
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
