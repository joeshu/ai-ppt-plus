from __future__ import annotations

import importlib.util
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


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("Astra iteration batch tests passed")
