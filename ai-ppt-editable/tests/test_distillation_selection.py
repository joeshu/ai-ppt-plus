from __future__ import annotations

from reconstruction.distillation_selection import DistillationSelectionPolicy, classify_record, select_records


def _base():
    return {
        "case_id": "case-1",
        "iteration": 1,
        "accepted": True,
        "rollback": False,
        "status": "repaired-needs-qa",
        "native_editability_valid": True,
        "semantic_accuracy": 1.0,
        "unauthorized_object_drift_count": 0,
        "pixel_fidelity_score": 0.94,
        "pixel_fidelity_delta": 0.03,
        "blocking_count": 0,
        "human_approved": True,
        "asset_user_choice_required_count": 0,
    }


def test_clean_improved_human_approved_record_is_positive():
    result = classify_record(_base())
    assert result["positive"] is True
    assert result["hard_negative"] is False


def test_rollback_is_hard_negative():
    record = _base()
    record.update({"accepted": False, "rollback": True, "status": "rolled-back-regression", "rollback_reasons": ["pixel_fidelity_decreased"]})
    result = classify_record(record)
    assert result["positive"] is False
    assert result["hard_negative"] is True
    assert "rollback" in result["negative_reasons"]
    assert "rollback:pixel_fidelity_decreased" in result["negative_reasons"]


def test_object_drift_is_hard_negative_even_if_visual_improves():
    record = _base()
    record["unauthorized_object_drift_count"] = 1
    result = classify_record(record)
    assert result["positive"] is False
    assert result["hard_negative"] is True
    assert "unauthorized_object_drift" in result["negative_reasons"]


def test_native_failure_is_hard_negative():
    record = _base()
    record["native_editability_valid"] = False
    result = classify_record(record)
    assert result["hard_negative"] is True
    assert "native_editability_failure" in result["negative_reasons"]


def test_missing_native_evidence_fails_closed_without_inventing_hard_negative():
    record = _base()
    record.pop("native_editability_valid")
    result = classify_record(record)
    assert result["positive"] is False
    assert result["hard_negative"] is False
    assert "native_editability_evidence_missing" in result["selection_reasons"]


def test_semantic_failure_is_hard_negative():
    record = _base()
    record["semantic_accuracy"] = 0.75
    result = classify_record(record)
    assert result["positive"] is False
    assert result["hard_negative"] is True
    assert "semantic_accuracy_failure" in result["negative_reasons"]
    assert "semantic_accuracy_not_perfect" in result["selection_reasons"]


def test_missing_semantic_evidence_is_rejected_fail_closed():
    record = _base()
    record.pop("semantic_accuracy")
    result = classify_record(record)
    assert result["positive"] is False
    assert result["hard_negative"] is False
    assert "semantic_accuracy_missing" in result["selection_reasons"]


def test_missing_human_approval_is_rejected_not_hard_negative():
    record = _base()
    record["human_approved"] = False
    batch = select_records([record])
    assert batch["positive_count"] == 0
    assert batch["hard_negative_count"] == 0
    assert batch["rejected_count"] == 1


def test_policy_can_allow_unapproved_for_experimental_selection():
    record = _base()
    record["human_approved"] = False
    result = classify_record(record, policy=DistillationSelectionPolicy(require_human_approval=False))
    assert result["positive"] is True


def test_asset_retry_exhaustion_count_is_hard_negative():
    record = _base()
    record["asset_user_choice_required_count"] = 1
    result = classify_record(record)
    assert result["hard_negative"] is True
    assert "asset_retry_exhausted" in result["negative_reasons"]
    assert "asset_user_choice_required" in result["selection_reasons"]


def test_legacy_asset_retry_exhaustion_bool_remains_supported():
    record = _base()
    record["asset_user_choice_required"] = True
    result = classify_record(record)
    assert result["hard_negative"] is True
    assert "asset_retry_exhausted" in result["negative_reasons"]


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("Distillation selection tests passed")
