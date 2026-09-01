#!/usr/bin/env python3
"""Regression tests for region-scoped proposals and safe candidate selection."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "candidate_controller.py"


def write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="candidate-controller-") as temp:
        root = Path(temp)
        report = write(root / "report.json", {"schema": "ai-ppt-plus/dual-comparison/v1", "valid": False, "issues": [{"severity": "major", "code": "text_overflow", "message": "title wraps", "slide": 2, "object_id": "title-2", "source_bbox": [10, 20, 300, 40]}]})
        plan_path = root / "plan.json"
        checked = subprocess.run([sys.executable, str(SCRIPT), "propose", "--report", str(report), "--base-candidate", "c1", "--output", str(plan_path)], capture_output=True, text=True, check=False)
        assert checked.returncode == 0, checked.stdout + checked.stderr
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        proposal = plan["proposals"][0]
        assert proposal["owner"] == "text" and proposal["scope"]["slide"] == 2, plan
        assert proposal["auto_apply"] is False and proposal["stop_conditions"]["max_repair_rounds"] == 3, plan

        accepted = write(root / "accepted.json", {"candidate_id": "c1--p", "weighted_score": 0.91, "gate": {"decision": "accept-for-human-review"}})
        rejected = write(root / "rejected.json", {"candidate_id": "c2--p", "weighted_score": 0.99, "gate": {"decision": "reject-and-rollback"}})
        selection_path = root / "selection.json"
        checked = subprocess.run([sys.executable, str(SCRIPT), "select", "--score", str(accepted), "--score", str(rejected), "--output", str(selection_path)], capture_output=True, text=True, check=False)
        assert checked.returncode == 0, checked.stdout + checked.stderr
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        assert selection["selected_candidate_id"] == "c1--p" and selection["release_eligible"] is False, selection
    print("candidate controller: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
