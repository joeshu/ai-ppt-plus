#!/usr/bin/env python3
"""Regression tests for resumable workflow-state/v1 readiness gates."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    package_revision = json.loads((ROOT / "assets/skill-package.json").read_text(encoding="utf-8"))["package_revision"]
    with tempfile.TemporaryDirectory(prefix="workflow-state-") as temp:
        project = Path(temp)
        files = {
            "deck-brief": "brief\n",
            "source-inventory": "sources\n",
            "outline": "outline\n",
            "design-system": "design\n",
            "route-decision": "route\n",
            "visual-plan": "plan\n",
            "visual-manifest": "manifest\n",
            "deck-strip": "strip\n",
        }
        artifacts = {}
        for name, content in files.items():
            path = project / f"{name}.artifact"
            path.write_text(content, encoding="utf-8")
            artifacts[name] = {"path": path.name, "required": True, "sha256": digest(path)}
        state = {
            "schema": "ai-ppt-plus/workflow-state/v1",
            "project_id": "workflow-fixture",
            "run_id": "run-1",
            "revision": "R1",
            "package_revision": package_revision,
            "phase": "visual-approved",
            "route": "visual-creation",
            "page_count": 2,
            "canvas_ratio": "16:9",
            "formal_text_authority": {"kind": "approved_outline", "path": "outline.artifact", "approved": True},
            "visual_authority": {"kind": "generated_visual_intermediate", "path": "visual-manifest.artifact", "approved": True},
            "artifacts": artifacts,
            "approvals": {"outline": True, "design_system": True, "visual": True, "human_closeout": False},
            "completed_stages": ["O0", "O1", "O2", "A1", "A2", "A3", "A4", "A5"],
            "open_blockers": [],
            "next_action": "start B0",
            "updated_at": "2026-08-30T00:00:00Z",
        }
        state_path = project / "workflow-state.json"
        write_json(state_path, state)
        report = project / "validation.json"
        command = [
            sys.executable, "scripts/validate_workflow_state.py", str(state_path),
            "--project-root", str(project), "--expected-pages", "2", "--strict", "--report", str(report),
        ]
        valid = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert valid.returncode == 0, valid.stdout + valid.stderr
        evidence = json.loads(report.read_text(encoding="utf-8"))
        assert evidence["valid"] is True
        assert set(evidence["evidence"]["required_artifacts"]) == set(files)

        broken = json.loads(state_path.read_text(encoding="utf-8"))
        broken["approvals"]["visual"] = False
        broken["artifacts"]["visual-plan"]["sha256"] = "0" * 64
        write_json(state_path, broken)
        invalid = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert invalid.returncode == 2, invalid.stdout + invalid.stderr
        assert "visual_approval_missing" in invalid.stdout
        assert "artifact_hash_mismatch" in invalid.stdout

        revision = json.loads(state_path.read_text(encoding="utf-8"))
        revision["phase"] = "revision-required"
        revision["artifacts"]["visual-plan"]["sha256"] = digest(project / "visual-plan.artifact")
        revision["open_blockers"] = [{"code": "copy_drift", "severity": "blocker", "owner_artifact": "visual-plan", "status": "open"}]
        write_json(state_path, revision)
        recoverable = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert recoverable.returncode == 0, recoverable.stdout + recoverable.stderr

    print("workflow state contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
