from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import validate_skill_package as validator


def _write_child(root: Path, name: str, revision: str) -> None:
    child = root / name
    (child / "assets").mkdir(parents=True)
    (child / "scripts").mkdir()
    (child / "SKILL.md").write_text(
        f"---\nname: {name}\n---\npackage_revision: {revision}\n",
        encoding="utf-8",
    )
    (child / "scripts" / "worker.py").write_text("pass\n", encoding="utf-8")
    (child / "assets" / "skill-package.json").write_text(
        json.dumps(
            {
                "schema": validator.PACKAGE_SCHEMA,
                "skill": name,
                "package_revision": revision,
                "entrypoint": "SKILL.md",
                "self_contained": {
                    "policy": "self-contained",
                    "required_dirs": ["assets", "scripts"],
                },
                "required_files": ["SKILL.md", "scripts/worker.py"],
                "managed_globs": ["scripts/*.py"],
            }
        ),
        encoding="utf-8",
    )


def test_bundled_worker_can_pin_revision_independent_of_parent(tmp_path: Path) -> None:
    _write_child(tmp_path, "ai-ppt-editable", "2026.09.18.02")
    issues: list[dict] = []
    evidence = validator.inspect_bundled_skills(
        tmp_path,
        {
            "bundled_skills": [
                {
                    "name": "ai-ppt-editable",
                    "root": "ai-ppt-editable",
                    "package_revision": "2026.09.18.02",
                }
            ]
        },
        "2026.09.17.01",
        issues,
    )

    assert not [issue for issue in issues if issue.get("code") == "bundled_skill_revision_mismatch"]
    assert evidence[0]["expected_revision"] == "2026.09.18.02"


def test_bundled_worker_revision_mismatch_uses_pinned_revision(tmp_path: Path) -> None:
    _write_child(tmp_path, "ai-ppt-editable", "2026.09.18.01")
    issues: list[dict] = []
    validator.inspect_bundled_skills(
        tmp_path,
        {
            "bundled_skills": [
                {
                    "name": "ai-ppt-editable",
                    "root": "ai-ppt-editable",
                    "package_revision": "2026.09.18.02",
                }
            ]
        },
        "2026.09.17.01",
        issues,
    )

    mismatch = next(issue for issue in issues if issue.get("code") == "bundled_skill_revision_mismatch")
    assert mismatch["expected"] == "2026.09.18.02"
    assert mismatch["observed"] == "2026.09.18.01"
