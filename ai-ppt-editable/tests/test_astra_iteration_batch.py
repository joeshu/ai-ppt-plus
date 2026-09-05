from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "evals" / "case-replay-12" / "run_astra_iteration_batch.py"
spec = importlib.util.spec_from_file_location("run_astra_iteration_batch", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def test_visual_regression_rolls_back():
    previous = {"pixel_fidelity_score": 0.90, "blocking_count": 1, "native_editability_valid": True}
    current = {"pixel_fidelity_score": 0.88, "blocking_count": 1, "native_editability_valid": True}
    result = module.regression_decision(previous, current)
    assert result["rollback"] is True
    assert "pixel_fidelity_decreased" in result["reasons"]


def test_blocker_increase_rolls_back():
    previous = {"pixel_fidelity_score": 0.88, "blocking_count": 1, "native_editability_valid": True}
    current = {"pixel_fidelity_score": 0.90, "blocking_count": 2, "native_editability_valid": True}
    result = module.regression_decision(previous, current)
    assert result["rollback"] is True
    assert "blocking_count_increased" in result["reasons"]


def test_native_editability_regression_rolls_back():
    previous = {"pixel_fidelity_score": 0.88, "blocking_count": 1, "native_editability_valid": True}
    current = {"pixel_fidelity_score": 0.91, "blocking_count": 1, "native_editability_valid": False}
    result = module.regression_decision(previous, current)
    assert result["rollback"] is True
    assert "native_editability_regressed" in result["reasons"]


def test_semantic_accuracy_regression_rolls_back_even_when_visual_improves():
    previous = {
        "pixel_fidelity_score": 0.88,
        "blocking_count": 1,
        "native_editability_valid": True,
        "semantic_accuracy": 1.0,
    }
    current = {
        "pixel_fidelity_score": 0.92,
        "blocking_count": 1,
        "native_editability_valid": True,
        "semantic_accuracy": 0.0,
    }
    result = module.regression_decision(previous, current)
    assert result["rollback"] is True
    assert result["semantic_accuracy_regressed"] is True
    assert "semantic_accuracy_regressed" in result["reasons"]


def test_improvement_is_accepted():
    previous = {"pixel_fidelity_score": 0.88, "blocking_count": 2, "native_editability_valid": True}
    current = {"pixel_fidelity_score": 0.91, "blocking_count": 1, "native_editability_valid": True}
    result = module.regression_decision(previous, current)
    assert result["rollback"] is False
    assert result["pixel_fidelity_delta"] > 0
    assert result["blocking_delta"] == -1


def test_small_visual_delta_can_use_tolerance():
    previous = {"pixel_fidelity_score": 0.9000, "blocking_count": 1, "native_editability_valid": True}
    current = {"pixel_fidelity_score": 0.8997, "blocking_count": 1, "native_editability_valid": True}
    result = module.regression_decision(previous, current, tolerance=0.001)
    assert result["rollback"] is False


def test_previous_visual_metrics_are_used_for_asset_resume_regression():
    previous = {"visual_metrics": {"pixel_fidelity_score": 0.90}, "blocking_count": 1, "native_editability_valid": True}
    current = {"pixel_fidelity_score": 0.87, "blocking_count": 1, "native_editability_valid": True}
    result = module.regression_decision(previous, current)
    assert result["rollback"] is True
    assert result["pixel_fidelity_delta"] == -0.03


def test_resume_ready_resolves_asset_layout_and_exact_resolved_ids():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        case_dir = tmp_path / "icon-case" / "iteration-1"
        case_dir.mkdir(parents=True)
        layout = case_dir / "asset-resolved-layout.json"
        layout.write_text('{"slides": []}\n', encoding="utf-8")
        (case_dir / "asset-resolution-report.json").write_text(json.dumps({
            "resolved": [
                {"object_id": "icon-new"},
                {"object_id": "icon-new"},
                {"object_id": "gradient-new"},
            ]
        }), encoding="utf-8")
        (case_dir / "resume-ready.json").write_text(json.dumps({
            "schema": "ai-ppt-plus/astra-resume-ready/v3",
            "ready": True,
            "status": "resume-ready",
            "layout": str(layout),
        }), encoding="utf-8")
        resolved, meta = module.resolve_resume_layout(tmp_path, "icon-case", 1)
        assert resolved == layout.resolve()
        assert meta["ready"] is True
        assert meta["resolved_object_ids"] == ["gradient-new", "icon-new"]
        assert meta["resolution_report"] == str((case_dir / "asset-resolution-report.json").resolve())


def test_unresolved_asset_does_not_resume():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        case_dir = tmp_path / "icon-case" / "iteration-1"
        case_dir.mkdir(parents=True)
        (case_dir / "resume-ready.json").write_text(json.dumps({
            "ready": False,
            "status": "external-asset",
            "layout": str(case_dir / "asset-resolved-layout.json"),
        }), encoding="utf-8")
        resolved, meta = module.resolve_resume_layout(tmp_path, "icon-case", 1)
        assert resolved is None
        assert meta["status"] == "external-asset"


def test_drift_allowlist_uses_only_applied_execution_actions():
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "repair-execution-report.json"
        report.write_text(json.dumps({
            "applied": [
                {"object_id": "text-1", "engine": "typography_repair"},
                {"object_id": "shape-2", "engine": "geometry_repair"},
                {"object_id": "text-1", "engine": "typography_repair"},
            ],
            "skipped": [{"object_id": "shape-skipped"}],
            "deferred": [{"object_id": "text-deferred"}],
            "regeneration_requests": [{"object_id": "icon-generated"}],
        }), encoding="utf-8")
        assert module.allowed_ids_from_execution_report(report) == {"text-1", "shape-2"}


def test_missing_execution_report_allows_no_normal_repair_drift():
    with tempfile.TemporaryDirectory() as tmp:
        assert module.allowed_ids_from_execution_report(Path(tmp) / "missing.json") == set()


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("Astra iteration batch tests passed")
