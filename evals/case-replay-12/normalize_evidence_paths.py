#!/usr/bin/env python3
"""Make generated case evidence portable inside a repository checkout."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def portable(value, root: Path, repo: Path):
    if isinstance(value, dict):
        return {key: portable(item, root, repo) for key, item in value.items()}
    if isinstance(value, list):
        return [portable(item, root, repo) for item in value]
    if not isinstance(value, str):
        return value
    for base in (root, repo):
        prefix = str(base.resolve()) + os.sep
        if value.startswith(prefix):
            return os.path.relpath(value, ROOT)
        if value == str(base.resolve()):
            return "."
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    changed = 0
    for path in sorted(root.rglob("*.json")):
        if path.name == "path-normalization-report.json":
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        normalized = portable(value, root, root.parents[1])
        if normalized != value:
            path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed += 1
    report = {"schema": "ai-ppt-plus/case-replay-path-normalization/v1", "root": ".", "json_files_changed": changed}
    (root / "path-normalization-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
