#!/usr/bin/env python3
"""Smoke-test the pinned perfect-source parity gate."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SYNCED_FILE_COUNT = 168
POST_BASELINE_EXCLUSIONS = frozenset({
    "assets/route-decision.template.json",
    "scripts/component_expander.py",
    "scripts/compose_pptx.py",
    "scripts/compare_visual.py",
    "scripts/compare_visual_deck.py",
    "scripts/delivery_check.py",
    "scripts/validate_project.py",
    "scripts/validate_signoff.py",
    "scripts/build_object_manifest.py",
    "scripts/distillation_loop.py",
    "references/automatic-distillation.md",
    "assets/schemas/distillation-case-registry.schema.json",
    "assets/schemas/distillation-score.schema.json",
    "assets/schemas/distillation-feedback.schema.json",
    "tests/test_distillation_loop.py",
    "scripts/candidate_controller.py",
    "references/candidate-repair-protocol.md",
    "assets/schemas/distillation-candidate-plan.schema.json",
    "assets/schemas/distillation-candidate-selection.schema.json",
    "tests/test_candidate_controller.py",
    "scripts/training_export.py",
    "references/training-data-protocol.md",
    "assets/schemas/distillation-human-approval.schema.json",
    "assets/schemas/distillation-training-example.schema.json",
    "assets/schemas/distillation-training-dataset.schema.json",
    "tests/test_training_export.py",
})


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="perfect-sync-") as temp:
        report = Path(temp) / "sync-validation.json"
        checked = subprocess.run(
            [sys.executable, "scripts/validate_perfect_sync.py", "--report", str(report)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert checked.returncode == 0, checked.stdout + checked.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["valid"] is True, data
        assert data["source"]["repository"] == "joeshu/ai-ppt-plus", data
        assert data["source"]["ref"] == "完美第一版", data
        assert data["source"]["commit"] == "d5dec0588fe87581112cbe1498ad4dac44f402e4", data
        manifest = json.loads((ROOT / "assets/upstream-perfect-sync.json").read_text(encoding="utf-8"))
        assert len(manifest["synced_files"]) == EXPECTED_SYNCED_FILE_COUNT, manifest
        excluded = {item["path"] for item in manifest["excluded_paths"]}
        assert POST_BASELINE_EXCLUSIONS <= excluded, manifest
        assert data["synced_file_count"] == EXPECTED_SYNCED_FILE_COUNT, data
    print("perfect-source parity gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
