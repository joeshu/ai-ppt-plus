from __future__ import annotations

import importlib.util
import json
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


def test_resume_ready_resolves_asset_layout(tmp_path: Path):
    case_dir = tmp_path / "icon-case" / "iteration-1"
    case_dir.mkdir(parents=True)
    layout = case_dir / "asset-resolved-layout.json"
    layout.write_text('{"slides": []}\n', encoding="utf-8")
    (case_dir / "resume-ready.json").write_text(json.dumps({
        "schema": "ai-ppt-plus/astra-resume-ready/v1",
        "ready": True,
        "status": "resume-ready",
        "layout": str(layout),
    }), encoding="utf-8")
    resolved, meta = module.resolve_resume_layout(tmp_path, "icon-case", 1)
    assert resolved == layout.resolve()
    assert meta["ready"] is True


def test_unresolved_asset_does_not_resume(tmp_path: Path):
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


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("Astra iteration batch tests passed")
