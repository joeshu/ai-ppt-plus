#!/usr/bin/env python3
"""Regression checks for three self-contained skill packages."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {
    "ai-ppt-plus": ROOT,
    "ai-ppt-visual-gen": ROOT / "ai-ppt-visual-gen",
    "ai-ppt-editable": ROOT / "ai-ppt-editable",
}


def frontmatter_value(text: str, key: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(key)}:\s*([^\s#]+)\s*$", text, re.MULTILINE)
    return match.group(1) if match else None


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    root_package = json.loads((ROOT / "assets" / "skill-package.json").read_text(encoding="utf-8"))
    routing = json.loads((ROOT / "assets" / "skill-routing.template.json").read_text(encoding="utf-8"))
    revision = root_package["package_revision"]
    bundled = {item["name"]: item["root"] for item in root_package["bundled_skills"]}
    assert bundled == {
        "ai-ppt-visual-gen": "ai-ppt-visual-gen",
        "ai-ppt-editable": "ai-ppt-editable",
    }

    for name, root in PACKAGES.items():
        package = json.loads((root / "assets" / "skill-package.json").read_text(encoding="utf-8"))
        assert package["schema"] == "ai-ppt-plus/skill-package/v2"
        assert package["skill"] == name
        assert package["package_revision"] == revision
        assert package["self_contained"]["policy"] == "self-contained"
        for directory in ("agents", "scripts", "references", "assets"):
            path = root / directory
            assert path.is_dir() and any(item.is_file() for item in path.rglob("*")), (name, directory)
        text = (root / "SKILL.md").read_text(encoding="utf-8")
        assert frontmatter_value(text, "name") == name
        assert frontmatter_value(text, "package_revision") == revision
        validated = subprocess.run(
            [sys.executable, str(root / "scripts" / "validate_skill_package.py"), "--skill-dir", str(root)],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert validated.returncode == 0, validated.stdout + validated.stderr

    assert {item["name"] for item in routing["skills"]} == set(PACKAGES)
    assert routing["bindings"]["visual_generation"]["runtime_entrypoint"].startswith("ai-ppt-visual-gen/")
    assert routing["bindings"]["reconstruction"]["runtime_entrypoint"].startswith("ai-ppt-editable/")
    assert routing["bindings"]["authoring"]["entrypoint"].startswith("ai-ppt-editable/")
    assert "GordenImage" not in json.dumps(routing, ensure_ascii=False)

    # The editable worker is pinned to the reconstruction core from the
    # perfect source branch. Its manifest is the source-of-truth parity gate;
    # only the explicitly documented package and orchestrator adapters are
    # outside that byte-identical set.
    editable_scripts = ROOT / "ai-ppt-editable" / "scripts"
    parity = subprocess.run(
        [sys.executable, str(editable_scripts / "validate_perfect_sync.py")],
        cwd=editable_scripts.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert parity.returncode == 0, parity.stdout + parity.stderr
    parity_manifest = json.loads((editable_scripts.parent / "assets" / "upstream-perfect-sync.json").read_text(encoding="utf-8"))
    assert parity_manifest["source"]["ref"] == "完美第一版"
    excluded = {item["path"] for item in parity_manifest["excluded_paths"]}
    assert len(parity_manifest["synced_files"]) >= 168
    assert len(parity_manifest["synced_files"]) + len(excluded) >= 202
    assert {"scripts/compare_visual.py", "scripts/compare_visual_deck.py", "scripts/delivery_check.py", "scripts/validate_signoff.py"} <= excluded

    # These two files are intentionally kept byte-identical with the root
    # orchestrator so the split worker remains callable by the v2 pipeline.
    for name in ("validate_handoff.py", "validate_route.py"):
        assert digest(ROOT / "scripts" / name) == digest(editable_scripts / name), name
    # The editable worker's run_pipeline.py is a post-baseline adapter with
    # perfect-first contract and object-level gates. It remains a callable
    # sibling entrypoint but is intentionally outside the shared mirror.
    assert (ROOT / "scripts" / "run_pipeline.py").is_file()
    assert (editable_scripts / "run_pipeline.py").is_file()
    # The visual worker owns richer A1-A5 planning/materialization validators;
    # they intentionally do not have to be byte-identical to root-side
    # compatibility helpers.  The runtime mirror policy covers only files
    # explicitly classified as shared, while this check protects the worker
    # entrypoints from disappearing.
    visual_scripts = ROOT / "ai-ppt-visual-gen" / "scripts"
    for name in (
        "atomic_output.py",
        "build_visual_generation_strip.py",
        "materialize_visual_generation_prompts.py",
        "run_tests.py",
        "validate_visual_assertions.py",
        "validate_visual_generation_plan.py",
    ):
        assert (visual_scripts / name).is_file(), name

    print("three self-contained skills: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
