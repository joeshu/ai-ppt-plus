#!/usr/bin/env python3
"""Check that local references in skill entrypoints resolve to real files.

Only explicit ``references/``, ``assets/`` and ``scripts/`` paths are checked.
Missing historical prose is reported as a blocker; this utility never invents
or restores documentation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from atomic_output import atomic_write_json


PATH_RE = re.compile(r"(?<![A-Za-z0-9_.-])((?:references|assets|scripts)(?:/[A-Za-z0-9_.-]+)+/?)(?![A-Za-z0-9_.-])")


def digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def scan(skill_root: Path) -> tuple[list[dict], list[dict]]:
    entry = skill_root / "SKILL.md"
    references: list[dict] = []
    issues: list[dict] = []
    if not entry.is_file():
        issues.append({"severity": "blocker", "code": "skill_entrypoint_missing", "path": str(entry)})
        return references, issues
    seen: set[tuple[str, int]] = set()
    for line_no, line in enumerate(entry.read_text(encoding="utf-8").splitlines(), start=1):
        for match in PATH_RE.finditer(line):
            relative = match.group(1)
            key = (relative, line_no)
            if key in seen:
                continue
            seen.add(key)
            target = (skill_root / relative).resolve()
            exists = target.is_file() or target.is_dir()
            record = {"skill": skill_root.name, "entrypoint": str(entry), "line": line_no,
                      "reference": relative, "resolved": str(target), "exists": exists,
                      "kind": "file" if target.is_file() else "directory" if target.is_dir() else "missing"}
            if target.is_file():
                record["sha256"] = digest(target)
            references.append(record)
            if not exists:
                issues.append({"severity": "blocker", "code": "skill_reference_missing",
                               "skill": skill_root.name, "line": line_no, "reference": relative,
                               "path": str(target),
                               "action": "Check git history for a reliable original; otherwise repair the stale reference without inventing contract text."})
    return references, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-dir", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--all-bundled", action="store_true")
    parser.add_argument("--output", "-o", required=True)
    args = parser.parse_args()
    root = Path(args.skill_dir).resolve()
    roots = [root]
    if args.all_bundled:
        roots.extend(path for path in (root / "ai-ppt-editable", root / "ai-ppt-visual-gen") if path.is_dir())
    references: list[dict] = []
    issues: list[dict] = []
    for skill_root in roots:
        found, found_issues = scan(skill_root)
        references.extend(found)
        issues.extend(found_issues)
    result = {"schema": "ai-ppt-plus/skill-reference-integrity/v1", "valid": not issues,
              "status": "passed" if not issues else "blocked", "root": str(root),
              "all_bundled": args.all_bundled, "references": references, "issues": issues,
              "historical_policy": "No missing historical file is synthesized; restore only from reliable git history or repair the stale reference and record the reason."}
    atomic_write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
