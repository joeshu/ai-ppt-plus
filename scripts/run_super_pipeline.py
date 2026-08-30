#!/usr/bin/env python3
"""Run the Super skill's deterministic A→B handoff or full QA pipeline.

``--mode handoff`` preserves the small compatibility chain used for quick
diagnostics. ``--mode full`` adds route validation, a formal handoff/v2, the
editable worker's complete technical pipeline, and a final handoff state.
Native image generation itself is an external runtime event; this coordinator
records and validates its evidence but never fakes it with code-drawn pixels.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from atomic_output import atomic_write_json, atomic_write_text


ROOT = Path(__file__).resolve().parents[1]
VISUAL = ROOT / "ai-ppt-visual-gen"
EDITABLE = ROOT / "ai-ppt-editable"
STEP_TIMEOUT_SECONDS = 1800


def read_json(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def as_text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def execute(name: str, command: list[str], cwd: Path, log_dir: Path, timeout: int = STEP_TIMEOUT_SECONDS) -> dict:
    """Run one stage with bounded time and durable stdout/stderr evidence."""
    started = time.perf_counter()
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"{name}.stdout.txt"
    stderr_path = log_dir / f"{name}.stderr.txt"
    failure = None
    try:
        completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)
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
        "cwd": str(cwd.resolve()),
        "ok": returncode == 0,
        "returncode": returncode,
        "stdout": str(stdout_path.resolve()),
        "stderr": str(stderr_path.resolve()),
        "timeout_seconds": timeout,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    if failure:
        result["failure"] = failure
    return result


def blocked(name: str, dependencies: list[str]) -> dict:
    """Represent a deliberately blocked stage without pretending it ran."""
    return {
        "name": name,
        "command": [],
        "cwd": str(ROOT.resolve()),
        "ok": False,
        "returncode": 2,
        "stdout": None,
        "stderr": None,
        "blocked_by": dependencies,
        "failure": "dependency_failed",
        "duration_ms": 0,
    }


def add_step(steps: list[dict], name: str, command: list[str], cwd: Path, log_dir: Path, *, deps: list[str] | None = None) -> dict:
    deps = deps or []
    failed = [item["name"] for item in steps if item["name"] in deps and not item.get("ok")]
    result = blocked(name, failed) if failed else execute(name, command, cwd, log_dir)
    steps.append(result)
    return result


def add_not_used(steps: list[dict], name: str, cwd: Path) -> dict:
    result = {"name": name, "command": [], "cwd": str(cwd.resolve()), "ok": True, "returncode": 0, "stdout": None, "stderr": None, "status": "not-used", "duration_ms": 0}
    steps.append(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--mode", choices=("handoff", "full"), default="handoff", help="compatibility handoff or full downstream QA")
    parser.add_argument("--visual-plan")
    parser.add_argument("--visual-manifest")
    parser.add_argument("--editable-layout", required=True)
    parser.add_argument("--output-deck", required=True)
    parser.add_argument("--expected-pages", type=int, required=True)
    parser.add_argument("--strip")
    parser.add_argument("--route-decision", help="required by --mode full; route-decision/v1 or v2")
    parser.add_argument("--workflow-state", help="orchestrator workflow-state/v1 contract")
    parser.add_argument("--require-workflow-state", action="store_true", help="require PROJECT_DIR/workflow-state.json or the path passed to --workflow-state")
    parser.add_argument("--handoff", help="formal handoff path; defaults to PROJECT/handoff.json")
    parser.add_argument("--font-dir")
    parser.add_argument("--human-signoff")
    parser.add_argument("--quality-score", type=float)
    parser.add_argument("--release", action="store_true", help="pass the strict release profile to the editable worker")
    parser.add_argument("--strict-qa", action="store_true", help="require typed editable manifests in the full worker QA")
    parser.add_argument("--execution-mode", choices=("dag", "linear"), default="dag")
    parser.add_argument("--parallel-workers", type=int, default=4)
    parser.add_argument("--cache-dir")
    parser.add_argument("--page-cache-dir")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    editable_layout = Path(args.editable_layout).resolve()
    output_deck = Path(args.output_deck).resolve()
    visual_plan = Path(args.visual_plan).resolve() if args.visual_plan else None
    visual_manifest = Path(args.visual_manifest).resolve() if args.visual_manifest else None
    route_path = Path(args.route_decision).resolve() if args.route_decision else None
    strip = Path(args.strip).resolve() if args.strip else project / "qa" / "visual-deck-strip.png"
    handoff = Path(args.handoff).resolve() if args.handoff else project / "handoff.json"
    workflow_state_enabled = bool(args.workflow_state or args.require_workflow_state)
    workflow_state_path = Path(args.workflow_state).resolve() if args.workflow_state else project / "workflow-state.json"
    run_id = datetime.now(timezone.utc).strftime("super-%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    log_dir = project / "super-pipeline-runs" / run_id
    visual_assertions = log_dir / "visual-assertions.json"
    report_path = Path(args.report).resolve() if args.report else project / "qa" / "super-pipeline.json"
    steps: list[dict] = []

    def finish(result: dict, code: int) -> int:
        atomic_write_json(report_path, result)
        print(json.dumps(result, ensure_ascii=False))
        return code

    if args.expected_pages < 1:
        return finish({"schema": "ai-ppt-plus/super-pipeline/v2", "valid": False, "status": "blocked", "code": "expected_pages_invalid", "run_id": run_id}, 2)
    if args.parallel_workers < 1:
        return finish({"schema": "ai-ppt-plus/super-pipeline/v2", "valid": False, "status": "blocked", "code": "parallel_workers_invalid", "run_id": run_id}, 2)
    if not project.is_dir() or not editable_layout.is_file():
        return finish({"schema": "ai-ppt-plus/super-pipeline/v2", "valid": False, "status": "blocked", "code": "project_or_editable_layout_missing", "project_dir": str(project), "editable_layout": str(editable_layout), "run_id": run_id}, 2)
    if args.mode == "full" and not route_path:
        return finish({"schema": "ai-ppt-plus/super-pipeline/v2", "valid": False, "status": "blocked", "code": "full_route_missing", "message": "--mode full requires --route-decision so visual authority cannot be inferred", "run_id": run_id}, 2)

    route_data = read_json(route_path)
    route = route_data.get("route")
    visual_route = route == "visual-creation" or (args.mode == "handoff" and not route_path and bool(visual_plan or visual_manifest))

    add_step(steps, "bundle", [sys.executable, str(ROOT / "scripts" / "validate_skill_package.py"), "--skill-dir", str(ROOT)], ROOT, log_dir)
    if args.mode == "full":
        environment_report = log_dir / "environment-report.json"
        environment_validation = log_dir / "environment-validation.json"
        add_step(steps, "environment", [
            sys.executable, str(ROOT / "scripts" / "probe_environment.py"),
            "--output", str(environment_report),
        ], ROOT, log_dir, deps=["bundle"])
        add_step(steps, "environment-contract", [
            sys.executable, str(ROOT / "scripts" / "validate_environment_contract.py"),
            "--report", str(environment_report), "--output", str(environment_validation),
        ], ROOT, log_dir, deps=["environment"])
        add_step(steps, "route", [
            sys.executable, str(ROOT / "scripts" / "validate_route.py"), str(route_path),
            "--require-files", "--expected-pages", str(args.expected_pages), "--require-confirmation",
            "--require-formal-content", "--report", str(log_dir / "route-validation.json"),
        ], ROOT, log_dir, deps=["bundle", "environment-contract"])

    if workflow_state_enabled:
        workflow_command = [
            sys.executable, str(ROOT / "scripts" / "validate_workflow_state.py"),
            str(workflow_state_path), "--project-root", str(project),
            "--expected-pages", str(args.expected_pages),
            "--report", str(log_dir / "workflow-state-validation.json"),
        ]
        if args.require_workflow_state:
            workflow_command.append("--strict")
        workflow_deps = ["bundle"]
        if args.mode == "full":
            workflow_deps.extend(["environment-contract", "route"])
        add_step(steps, "workflow-state", workflow_command, ROOT, log_dir, deps=workflow_deps)

    visual_deps = ["bundle"] + (["route"] if args.mode == "full" else [])
    if workflow_state_enabled:
        visual_deps.append("workflow-state")
    if visual_route and visual_plan and visual_manifest:
        add_step(steps, "A-visual", [
            sys.executable, str(VISUAL / "scripts" / "run_visual_pipeline.py"), str(visual_plan),
            "--expected-pages", str(args.expected_pages), "--manifest", str(visual_manifest),
            "--strip", str(strip), "--report", str(log_dir / "visual-pipeline.json"),
        ], VISUAL, log_dir, deps=visual_deps)
    elif visual_route:
        steps.append({"name": "A-visual", "command": [], "cwd": str(VISUAL.resolve()), "ok": False, "returncode": 2, "stdout": None, "stderr": None, "failure": "visual_plan_or_manifest_missing", "duration_ms": 0})
    else:
        add_not_used(steps, "A-visual", VISUAL)

    compose_deps = ["bundle"] + (["route"] if args.mode == "full" else []) + (["workflow-state"] if workflow_state_enabled else []) + ["A-visual"]
    add_step(steps, "B-editable-compose", [sys.executable, str(EDITABLE / "scripts" / "compose_pptx.py"), str(editable_layout), str(output_deck)], EDITABLE, log_dir, deps=compose_deps)
    add_step(steps, "B-editable-inspect", [sys.executable, str(EDITABLE / "scripts" / "inspect_pptx.py"), str(output_deck), "--report", str(project / "qa" / "editable-inspection.json")], EDITABLE, log_dir, deps=["B-editable-compose"])

    if args.mode == "full":
        handoff_command = [
            sys.executable, str(ROOT / "scripts" / "build_handoff.py"), str(project), "--output", str(handoff),
            "--expected-pages", str(args.expected_pages), "--run-id", run_id, "--editable-layout", str(editable_layout),
            "--pptx", str(output_deck), "--strip", str(strip), "--current-stage", "reconstruction",
            "--gate-status", "in-progress", "--next-action", "run editable technical QA",
            "--latest-check", "B-editable-inspect", "--route-decision", str(route_path),
        ]
        if visual_plan:
            handoff_command.extend(["--visual-plan", str(visual_plan)])
        if visual_manifest:
            handoff_command.extend(["--visual-manifest", str(visual_manifest)])
        if workflow_state_enabled:
            handoff_command.extend(["--workflow-state", str(workflow_state_path)])
        if visual_assertions.is_file():
            handoff_command.extend(["--visual-assertions", str(visual_assertions)])
        add_step(steps, "handoff-build", handoff_command, ROOT, log_dir, deps=["B-editable-inspect"])

        qa_command = [
            sys.executable, str(EDITABLE / "scripts" / "run_pipeline.py"), str(project),
            "--deck", str(output_deck), "--expected-pages", str(args.expected_pages),
            "--execution-mode", args.execution_mode, "--parallel-workers", str(args.parallel_workers),
            "--output-dir", str(log_dir / "editable-qa"), "--route-decision", str(route_path),
            "--require-route", "--require-formal-content", "--handoff", str(handoff),
        ]
        if visual_route and visual_plan and visual_manifest:
            qa_command.extend(["--visual-generation-plan", str(visual_plan), "--visual-generation-manifest", str(visual_manifest), "--require-visual-generation"])
        if args.font_dir:
            qa_command.extend(["--font-dir", str(Path(args.font_dir).resolve())])
        if args.cache_dir:
            qa_command.extend(["--cache-dir", str(Path(args.cache_dir).resolve())])
        if args.page_cache_dir:
            qa_command.extend(["--page-cache-dir", str(Path(args.page_cache_dir).resolve())])
        if args.no_cache:
            qa_command.append("--no-cache")
        if args.strict_qa:
            qa_command.extend(["--require-editability", "--require-object-manifest", "--require-manifest-registry", "--require-text-model"])
        if args.release:
            qa_command.append("--release")
            if args.human_signoff:
                qa_command.extend(["--human-signoff", str(Path(args.human_signoff).resolve())])
            if args.quality_score is not None:
                qa_command.extend(["--quality-score", str(args.quality_score)])
        add_step(steps, "B-editable-qa", qa_command, EDITABLE, log_dir, deps=["handoff-build"])

        qa_ok = steps[-1].get("ok")
        final_stage = "validated" if qa_ok else "revision-required"
        final_gate = "technical-passed" if qa_ok else "blocked"
        final_command = [
            sys.executable, str(ROOT / "scripts" / "build_handoff.py"), str(project), "--output", str(handoff),
            "--expected-pages", str(args.expected_pages), "--run-id", run_id, "--editable-layout", str(editable_layout),
            "--pptx", str(output_deck), "--strip", str(strip), "--current-stage", final_stage,
            "--gate-status", final_gate, "--latest-check", "B-editable-qa",
            "--next-action", "human closeout and release" if qa_ok else "repair failed editable QA gates",
        ]
        if qa_ok:
            final_command.extend(["--completed-pages", ",".join(str(index) for index in range(1, args.expected_pages + 1))])
        else:
            final_command.extend(["--remaining-pages", ",".join(str(index) for index in range(1, args.expected_pages + 1)), "--blocker", "editable technical QA failed"])
        if route_path:
            final_command.extend(["--route-decision", str(route_path)])
        if visual_plan:
            final_command.extend(["--visual-plan", str(visual_plan)])
        if visual_manifest:
            final_command.extend(["--visual-manifest", str(visual_manifest)])
        if workflow_state_enabled:
            final_command.extend(["--workflow-state", str(workflow_state_path)])
        if visual_assertions.is_file():
            final_command.extend(["--visual-assertions", str(visual_assertions)])
        add_step(steps, "handoff-finalize", final_command, ROOT, log_dir, deps=["B-editable-qa"])
        add_step(steps, "handoff-validate", [sys.executable, str(ROOT / "scripts" / "validate_handoff.py"), str(handoff), "--report", str(log_dir / "handoff-validation.json")], ROOT, log_dir, deps=["handoff-finalize"])

    valid = all(step.get("ok") for step in steps)
    result = {
        "schema": "ai-ppt-plus/super-pipeline/v2",
        "valid": valid,
        "status": "passed" if valid else "blocked",
        "mode": args.mode,
        "run_id": run_id,
        "project_dir": str(project),
        "handoff": str(handoff) if args.mode == "full" else None,
        "workflow_state": str(workflow_state_path) if workflow_state_enabled else None,
        "visual_skill": str(VISUAL),
        "editable_skill": str(EDITABLE),
        "output_deck": str(output_deck),
        "steps": steps,
        "failed_steps": [step["name"] for step in steps if not step.get("ok")],
        "external_events": {"native_image_generation": "required-before-A-visual-run; not invoked by this Python coordinator"},
    }
    return finish(result, 0 if valid else 2)


if __name__ == "__main__":
    raise SystemExit(main())
