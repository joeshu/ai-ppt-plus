#!/usr/bin/env python3
"""Run the deterministic A1-A5 evidence stages around native image generation."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from atomic_output import atomic_write_json


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"


def has_visual_assertions(plan: Path) -> bool:
    try:
        data = json.loads(plan.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return any(isinstance(slide, dict) and slide.get("visual_assertions") is not None for slide in (data.get("slides") or [])) if isinstance(data, dict) else False


def run(name: str, command: list[str]) -> dict:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
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
    parser.add_argument("plan")
    parser.add_argument("--expected-pages", type=int, required=True)
    parser.add_argument("--manifest")
    parser.add_argument("--materialize", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--strip")
    parser.add_argument("--image-pptx")
    parser.add_argument("--report")
    args = parser.parse_args()
    plan = Path(args.plan).resolve()
    manifest = Path(args.manifest).resolve() if args.manifest else None
    steps = [
        run("skill-package", [
            sys.executable,
            str(SCRIPT_DIR / "validate_skill_package.py"),
            "--skill-dir",
            str(ROOT),
        ])
    ]
    if steps[-1]["ok"] and args.materialize:
        command = [
            sys.executable,
            str(SCRIPT_DIR / "materialize_visual_generation_prompts.py"),
            str(plan),
            "--in-place",
        ]
        if args.force:
            command.append("--force")
        steps.append(run("materialize-prompts", command))
    if all(item["ok"] for item in steps) and manifest and args.strip:
        steps.append(run("deck-strip", [
            sys.executable,
            str(SCRIPT_DIR / "build_visual_generation_strip.py"),
            str(manifest),
            "--output",
            str(Path(args.strip).resolve()),
            "--expected-pages",
            str(args.expected_pages),
            "--record-in-manifest",
        ]))
    if all(item["ok"] for item in steps):
        command = [
            sys.executable,
            str(SCRIPT_DIR / "validate_visual_generation_plan.py"),
            str(plan),
            "--expected-pages",
            str(args.expected_pages),
        ]
        if manifest:
            command.extend(["--manifest", str(manifest), "--require-evidence"])
        steps.append(run("visual-generation", command))
    if all(item["ok"] for item in steps) and manifest and has_visual_assertions(plan):
        assertions_report = Path(args.report).resolve().with_name("visual-assertions.json") if args.report else plan.parent / "visual-assertions.json"
        steps.append(run("visual-assertions", [
            sys.executable,
            str(SCRIPT_DIR / "validate_visual_assertions.py"),
            str(plan),
            "--manifest", str(manifest),
            "--expected-pages", str(args.expected_pages),
            "--report", str(assertions_report),
        ]))
    if all(item["ok"] for item in steps) and manifest and args.image_pptx:
        steps.append(run("image-pptx", [
            sys.executable,
            str(SCRIPT_DIR / "compose_image_pptx.py"),
            str(manifest),
            str(Path(args.image_pptx).resolve()),
        ]))
    valid = all(item["ok"] for item in steps)
    result = {
        "schema": "ai-ppt-visual-gen/pipeline/v1",
        "valid": valid,
        "status": "passed" if valid else "blocked",
        "plan": str(plan),
        "manifest": str(manifest) if manifest else None,
        "steps": steps,
        "note": "Native raster generation occurs between materialization and evidence validation.",
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
