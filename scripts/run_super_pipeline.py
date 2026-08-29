#!/usr/bin/env python3
"""Validate and chain visual-worker evidence into editable-worker composition."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from atomic_output import atomic_write_json


ROOT = Path(__file__).resolve().parents[1]
VISUAL = ROOT / "ai-ppt-visual-gen"
EDITABLE = ROOT / "ai-ppt-editable"


def execute(name: str, command: list[str], cwd: Path) -> dict:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    return {
        "name": name,
        "command": command,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--visual-plan", required=True)
    parser.add_argument("--visual-manifest", required=True)
    parser.add_argument("--editable-layout", required=True)
    parser.add_argument("--output-deck", required=True)
    parser.add_argument("--expected-pages", type=int, required=True)
    parser.add_argument("--strip")
    parser.add_argument("--report")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    strip = Path(args.strip).resolve() if args.strip else project / "qa" / "visual-deck-strip.png"
    steps = [
        execute("bundle", [
            sys.executable,
            str(ROOT / "scripts" / "validate_skill_package.py"),
            "--skill-dir",
            str(ROOT),
        ], ROOT)
    ]
    if steps[-1]["ok"]:
        steps.append(execute("A-visual", [
            sys.executable,
            str(VISUAL / "scripts" / "run_visual_pipeline.py"),
            str(Path(args.visual_plan).resolve()),
            "--manifest",
            str(Path(args.visual_manifest).resolve()),
            "--expected-pages",
            str(args.expected_pages),
            "--strip",
            str(strip),
        ], VISUAL))
    if all(item["ok"] for item in steps):
        steps.append(execute("B-editable-compose", [
            sys.executable,
            str(EDITABLE / "scripts" / "compose_pptx.py"),
            str(Path(args.editable_layout).resolve()),
            str(Path(args.output_deck).resolve()),
        ], EDITABLE))
    if all(item["ok"] for item in steps):
        steps.append(execute("B-editable-inspect", [
            sys.executable,
            str(EDITABLE / "scripts" / "inspect_pptx.py"),
            str(Path(args.output_deck).resolve()),
            "--report",
            str(project / "qa" / "editable-inspection.json"),
        ], EDITABLE))
    valid = all(item["ok"] for item in steps)
    result = {
        "schema": "ai-ppt-plus/super-pipeline/v1",
        "valid": valid,
        "status": "passed" if valid else "blocked",
        "project_dir": str(project),
        "visual_skill": str(VISUAL),
        "editable_skill": str(EDITABLE),
        "steps": steps,
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
