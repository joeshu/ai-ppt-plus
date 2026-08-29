#!/usr/bin/env python3
"""Regression checks for the three-entrypoint, single-runtime architecture."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "ai-ppt-plus": ("orchestrator", ROOT / "SKILL.md"),
    "ai-ppt-visual-gen": ("visual-worker", ROOT / "ai-ppt-visual-gen" / "SKILL.md"),
    "ai-ppt-editable": ("editable-worker", ROOT / "ai-ppt-editable" / "SKILL.md"),
}


def frontmatter_value(text: str, key: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(key)}:\s*([^\s#]+)\s*$", text, re.MULTILINE)
    return match.group(1) if match else None


def main() -> int:
    package = json.loads((ROOT / "assets" / "skill-package.json").read_text(encoding="utf-8"))
    routing = json.loads((ROOT / "assets" / "skill-routing.template.json").read_text(encoding="utf-8"))
    revision = package["package_revision"]

    entries = {item["name"]: item for item in package["skill_entries"]}
    assert set(entries) == set(EXPECTED), entries
    assert package["shared_runtime"] == {
        "policy": "single-source",
        "roots": ["scripts", "assets", "references"],
    }

    for name, (role, path) in EXPECTED.items():
        assert entries[name]["role"] == role
        text = path.read_text(encoding="utf-8")
        assert frontmatter_value(text, "name") == name
        assert frontmatter_value(text, "package_revision") == revision

    assert {item["name"] for item in routing["skills"]} == set(EXPECTED)
    assert routing["bindings"]["orchestrator"]["skill"] == "ai-ppt-plus"
    assert routing["bindings"]["visual_generation"]["skill"] == "ai-ppt-visual-gen"
    assert routing["bindings"]["reconstruction"]["skill"] == "ai-ppt-editable"
    assert routing["bindings"]["authoring"]["kind"] == "adapter"
    assert "Presentations" not in {item["name"] for item in routing["skills"]}
    assert "GordenImage" not in json.dumps(routing, ensure_ascii=False)

    for worker in (ROOT / "ai-ppt-visual-gen", ROOT / "ai-ppt-editable"):
        assert not (worker / "scripts").exists(), "shared scripts must not be copied into worker entrypoints"
        assert not (worker / "assets").exists(), "shared assets must not be copied into worker entrypoints"
        assert not (worker / "references").exists(), "shared references must not be copied into worker entrypoints"

    print("three-skill split: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
