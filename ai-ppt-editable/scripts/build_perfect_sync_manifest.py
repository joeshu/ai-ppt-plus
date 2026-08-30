#!/usr/bin/env python3
"""Build the pinned byte-parity manifest for the perfect source branch."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from atomic_output import atomic_write_json


SOURCE_AREAS = ("SKILL.md", "agents", "assets", "evals", "examples", "references", "scripts", "tests")
EXCLUDED_PATHS = [
    {"path": "SKILL.md", "reason": "standalone worker entrypoint and identity"},
    {"path": "agents/openai.yaml", "reason": "standalone worker interface and identity"},
    {"path": "assets/skill-package.json", "reason": "standalone package manifest"},
    {"path": "assets/skill-routing.template.json", "reason": "standalone worker routing contract"},
    {"path": "assets/schemas/skill-routing.schema.json", "reason": "standalone worker routing schema"},
    {"path": "assets/upstream-perfect-sync.json", "reason": "generated parity manifest"},
    {"path": "assets/route-decision-native-authoring.template.json", "reason": "post-baseline native-authoring compatibility extension"},
    {"path": "assets/schemas/route-decision.schema.json", "reason": "post-baseline route schema extension"},
    {"path": "evals/editable-trigger-cases.yaml", "reason": "standalone worker trigger extension"},
    {"path": "requirements-ci.txt", "reason": "standalone package dependency pin"},
    {"path": "references/perfect-source-sync.md", "reason": "standalone synchronization documentation"},
    {"path": "scripts/build_perfect_sync_manifest.py", "reason": "standalone synchronization utility"},
    {"path": "scripts/inspect_editable_objects.py", "reason": "post-baseline page-scoped object audit correctness fix"},
    {"path": "scripts/pipeline_engine.py", "reason": "post-baseline orchestrator runtime compatibility adapter"},
    {"path": "scripts/run_pipeline.py", "reason": "post-baseline orchestrator integration adapter"},
    {"path": "scripts/validate_handoff.py", "reason": "post-baseline v2 handoff compatibility adapter"},
    {"path": "scripts/validate_perfect_sync.py", "reason": "standalone synchronization validator"},
    {"path": "scripts/validate_skill_package.py", "reason": "standalone package validator"},
    {"path": "scripts/validate_routing_contract.py", "reason": "standalone worker routing validator"},
    {"path": "scripts/validate_route.py", "reason": "post-baseline v2/native-authoring route compatibility adapter"},
    {"path": "scripts/validate_visual_generation_plan.py", "reason": "post-baseline compatibility validator"},
    {"path": "scripts/validate_workflow_state.py", "reason": "post-baseline compatibility validator"},
    {"path": "tests/test_editable_object_audit.py", "reason": "standalone page-scoped audit regression"},
    {"path": "tests/test_perfect_sync.py", "reason": "standalone synchronization regression"},
    {"path": "tests/test_self_contained.py", "reason": "standalone package smoke test"},
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_files(source_root: Path) -> list[Path]:
    files: list[Path] = []
    for relative in SOURCE_AREAS:
        path = source_root / relative
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(candidate for candidate in path.rglob("*") if candidate.is_file())
        else:
            raise FileNotFoundError(f"source area missing: {relative}")
    return sorted(files, key=lambda path: path.relative_to(source_root).as_posix())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, help="checkout or extracted tree for 完美第一版")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--target-dir", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    source_root = Path(args.source_dir).resolve()
    target_root = Path(args.target_dir).resolve()
    output = Path(args.output).resolve() if args.output else target_root / "assets" / "upstream-perfect-sync.json"
    excluded = {item["path"] for item in EXCLUDED_PATHS}
    issues: list[dict] = []
    synced_files: list[dict] = []
    try:
        candidates = source_files(source_root)
    except Exception as exc:
        candidates = []
        issues.append({"severity": "blocker", "code": "source_tree_incomplete", "message": f"{type(exc).__name__}: {exc}"})

    for source_path in candidates:
        relative = source_path.relative_to(source_root).as_posix()
        if relative in excluded:
            continue
        target_path = target_root / relative
        if not target_path.is_file():
            issues.append({"severity": "blocker", "code": "target_file_missing", "path": relative})
            continue
        source_hash = sha256(source_path)
        target_hash = sha256(target_path)
        executable = os.access(source_path, os.X_OK)
        target_executable = os.access(target_path, os.X_OK)
        if source_hash != target_hash:
            issues.append({"severity": "blocker", "code": "target_hash_mismatch", "path": relative, "expected": source_hash, "observed": target_hash})
        if executable != target_executable:
            issues.append({"severity": "blocker", "code": "target_mode_mismatch", "path": relative, "expected_executable": executable, "observed_executable": target_executable})
        synced_files.append({"source_path": relative, "target_path": relative, "sha256": source_hash, "executable": executable})

    manifest = {
        "schema": "ai-ppt-editable/upstream-perfect-sync/v1",
        "source": {
            "repository": "joeshu/ai-ppt-plus",
            "ref": "完美第一版",
            "commit": args.source_commit,
            "path_scope": "repository package areas copied under ai-ppt-editable/",
        },
        "mapping": {"mode": "byte-identical", "source_root": ".", "target_root": "ai-ppt-editable"},
        "synced_files": synced_files,
        "excluded_paths": EXCLUDED_PATHS,
        "generated_by": "scripts/build_perfect_sync_manifest.py",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output, manifest)
    result = {
        "schema": "ai-ppt-editable/upstream-perfect-sync-build/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "source_root": str(source_root),
        "target_root": str(target_root),
        "output": str(output),
        "source_commit": args.source_commit,
        "synced_file_count": len(synced_files),
        "issues": issues,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
