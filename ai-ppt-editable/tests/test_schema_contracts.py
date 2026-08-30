#!/usr/bin/env python3
"""Validate the checked-in core JSON contracts without third-party tooling."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from schema_contract import validate  # noqa: E402


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    schemas = ROOT / "assets/schemas"
    report_index = read(ROOT / "assets/report-index.template.json")
    assert not validate(report_index, read(schemas / "report-index.schema.json"))
    routing = read(ROOT / "assets/skill-routing.template.json")
    assert not validate(routing, read(schemas / "skill-routing.schema.json"))
    manifest_registry = read(ROOT / "assets/manifest-registry.template.json")
    assert not validate(manifest_registry, read(schemas / "manifest-registry.schema.json"))

    envelope = {
        "schema": "ai-ppt-plus/report-envelope/v1",
        "report_type": "project-aggregate",
        "valid": True,
        "status": "passed",
        "technical_valid": True,
        "human_review_required": True,
        "human_review_status": "pending",
        "release_eligible": False,
        "release_status": "blocked-pending-signoff",
        "issues": [],
        "source_references": [],
    }
    assert not validate(envelope, read(schemas / "report-envelope.schema.json"))
    bad_envelope = copy.deepcopy(envelope)
    del bad_envelope["technical_valid"]
    assert validate(bad_envelope, read(schemas / "report-envelope.schema.json"))

    bundle = {
        **envelope,
        "report_type": "report-bundle-validation",
        "technical_status": "passed",
        "validation_scope": "full",
        "full_deck_validation_required": False,
        "deck_sha256": "a" * 64,
        "report_index_sha256": "b" * 64,
        "checks": [],
        "pipeline_result_path": "pipeline-result.json",
        "pipeline_result_sha256": "c" * 64,
        "project_report_path": "project-report.json",
        "report_index_path": "report-index.json",
    }
    assert not validate(bundle, read(schemas / "report-bundle-validation.schema.json"))

    pipeline = {
        "schema": "ai-ppt-plus/pipeline-run/v2",
        "valid": True,
        "status": "passed",
        "technical_valid": True,
        "technical_status": "passed",
        "validation_scope": "full",
        "full_deck_validation_required": False,
        "release_eligible": False,
        "release_status": "not_run",
        "human_review_required": True,
        "human_review_status": "pending",
        "run_id": "run-test",
        "project": "project",
        "deck": "deck.pptx",
        "deck_sha256": "a" * 64,
        "source_references": [],
        "run_dir": "run",
        "steps": [],
        "failed_steps": [],
        "technical_failed_steps": [],
        "next_state": "validated",
        "human_visual_review_required": True,
        "human_signoff_required": True,
        "execution": {"mode": "dag", "tasks_total": 0, "cache_hits": 0},
    }
    assert not validate(pipeline, read(schemas / "pipeline-run.schema.json"))
    print("schema contracts: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())