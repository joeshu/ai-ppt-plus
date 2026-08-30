#!/usr/bin/env python3
"""Run the deterministic A1-A5 evidence stages around native image generation."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from atomic_output import atomic_write_json, atomic_write_text


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"


def has_visual_assertions(plan: Path) -> bool:
    try:
        data = json.loads(plan.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return any(isinstance(slide, dict) and slide.get("visual_assertions") is not None for slide in (data.get("slides") or [])) if isinstance(data, dict) else False


def as_text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def run(name: str, command: list[str], timeout: int, log_dir: Path) -> dict:
    """Run one deterministic evidence stage with bounded, durable logs."""
    started = time.perf_counter()
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"{name}.stdout.txt"
    stderr_path = log_dir / f"{name}.stderr.txt"
    failure = None
    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False)
        stdout = as_text(completed.stdout)
        stderr = as_text(completed.stderr)
        returncode = completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = as_text(exc.stdout)
        stderr = as_text(exc.stderr) + f"\nstep timed out after {timeout}s\n"
        returncode = 124
        failure = "timeout"
    except OSError as exc:
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}\n"
        returncode = 127
        failure = "spawn-failed"
    atomic_write_text(stdout_path, stdout)
    atomic_write_text(stderr_path, stderr)
    result = {
        "name": name,
        "command": command,
        "ok": returncode == 0,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_path": str(stdout_path.resolve()),
        "stderr_path": str(stderr_path.resolve()),
        "timeout_seconds": timeout,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    if failure:
        result["failure"] = failure
    return result


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
    parser.add_argument("--timeout-seconds", type=int, default=600, help="per-stage subprocess timeout")
    args = parser.parse_args()
    if args.timeout_seconds < 1:
        print(json.dumps({"schema": "ai-ppt-visual-gen/pipeline/v1", "valid": False, "status": "blocked", "code": "timeout_invalid"}, ensure_ascii=False))
        return 2
    plan = Path(args.plan).resolve()
    manifest = Path(args.manifest).resolve() if args.manifest else None
    report_path = Path(args.report).resolve() if args.report else None
    log_dir = (report_path.parent if report_path else plan.parent) / "visual-pipeline-logs"
    steps = [
        run("skill-package", [
            sys.executable,
            str(SCRIPT_DIR / "validate_skill_package.py"),
            "--skill-dir",
            str(ROOT),
        ], args.timeout_seconds, log_dir)
    ]
    if steps[-1]["ok"]:
        steps.append(run("narrative-gate", [
            sys.executable,
            str(SCRIPT_DIR / "validate_visual_generation_plan.py"),
            str(plan),
            "--expected-pages",
            str(args.expected_pages),
            "--narrative-only",
            "--require-narrative-approval",
        ], args.timeout_seconds, log_dir))
    if steps[-1]["ok"] and args.materialize:
        command = [
            sys.executable,
            str(SCRIPT_DIR / "materialize_visual_generation_prompts.py"),
            str(plan),
            "--in-place",
        ]
        if args.force:
            command.append("--force")
        steps.append(run("materialize-prompts", command, args.timeout_seconds, log_dir))
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
        ], args.timeout_seconds, log_dir))
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
        command.append("--require-narrative-approval")
        steps.append(run("visual-generation", command, args.timeout_seconds, log_dir))
    if all(item["ok"] for item in steps) and manifest and has_visual_assertions(plan):
        assertions_report = Path(args.report).resolve().with_name("visual-assertions.json") if args.report else plan.parent / "visual-assertions.json"
        steps.append(run("visual-assertions", [
            sys.executable,
            str(SCRIPT_DIR / "validate_visual_assertions.py"),
            str(plan),
            "--manifest", str(manifest),
            "--expected-pages", str(args.expected_pages),
            "--report", str(assertions_report),
        ], args.timeout_seconds, log_dir))
    if all(item["ok"] for item in steps) and manifest and args.image_pptx:
        steps.append(run("image-pptx", [
            sys.executable,
            str(SCRIPT_DIR / "compose_image_pptx.py"),
            str(manifest),
            str(Path(args.image_pptx).resolve()),
        ], args.timeout_seconds, log_dir))
    valid = all(item["ok"] for item in steps)
    result = {
        "schema": "ai-ppt-visual-gen/pipeline/v1",
        "valid": valid,
        "status": "passed" if valid else "blocked",
        "plan": str(plan),
        "manifest": str(manifest) if manifest else None,
        "log_dir": str(log_dir.resolve()),
        "timeout_seconds": args.timeout_seconds,
        "steps": steps,
        "note": "Native raster generation occurs between materialization and evidence validation.",
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
