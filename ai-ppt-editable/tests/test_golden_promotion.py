from __future__ import annotations

from reconstruction.golden_promotion import GoldenPromotionPolicy, build_promotion_manifest, evaluate_case


def _semantic_audit(**overrides):
    audit = {
        "valid": True,
        "accuracy": 1.0,
        "error_count": 0,
        "warning_count": 0,
        "expected_object_count": 8,
        "audited_object_count": 8,
    }
    audit.update(overrides)
    return audit


def _record(iteration: int, **overrides):
    record = {
        "case_id": "case-1",
        "iteration": iteration,
        "accepted": True,
        "rollback": False,
        "unauthorized_object_drift_count": 0,
        "native_editability_valid": True,
        "blocking_count": 0,
        "pixel_fidelity_score": 0.96,
        "semantic_accuracy": 1.0,
        "semantic_audit": _semantic_audit(),
        "source_accepted_iteration": max(0, iteration - 1),
        "source_layout": f"iteration-{max(0, iteration - 1)}/layout.json",
        "human_approved": True,
        "artifacts": {"pptx": f"iteration-{iteration}/editable.pptx"},
    }
    record.update(overrides)
    return record


def test_two_consecutive_clean_iterations_are_promotable():
    result = evaluate_case([_record(1), _record(2)])
    assert result["promotable"] is True
    assert result["stable_streak"] == 2
    assert result["candidate_iteration"] == 2
    assert result["candidate_semantic_evidence"]["semantic_object_coverage_complete"] is True
    assert result["candidate_source_lineage"]["complete"] is True
    assert result["candidate_source_lineage"]["source_accepted_iteration"] == 1


def test_missing_semantic_accuracy_fails_closed():
    result = evaluate_case([_record(1), _record(2, semantic_accuracy=None)])
    assert result["promotable"] is False
    assert "missing_semantic_accuracy" in result["evaluations"][-1]["reasons"]


def test_missing_semantic_audit_fails_closed_even_with_perfect_summary():
    result = evaluate_case([_record(1), _record(2, semantic_audit=None)])
    assert result["promotable"] is False
    assert "semantic_audit_missing" in result["evaluations"][-1]["reasons"]


def test_incomplete_semantic_object_coverage_fails_closed():
    result = evaluate_case([
        _record(1),
        _record(2, semantic_audit=_semantic_audit(expected_object_count=8, audited_object_count=7)),
    ])
    assert result["promotable"] is False
    assert "semantic_audit_incomplete" in result["evaluations"][-1]["reasons"]


def test_semantic_audit_errors_fail_closed():
    result = evaluate_case([
        _record(1),
        _record(2, semantic_audit=_semantic_audit(valid=False, error_count=1)),
    ])
    assert result["promotable"] is False
    reasons = result["evaluations"][-1]["reasons"]
    assert "semantic_audit_invalid" in reasons
    assert "semantic_audit_errors_present" in reasons


def test_semantic_summary_and_audit_accuracy_must_match():
    result = evaluate_case([
        _record(1),
        _record(2, semantic_accuracy=1.0, semantic_audit=_semantic_audit(accuracy=0.75)),
    ])
    assert result["promotable"] is False
    reasons = result["evaluations"][-1]["reasons"]
    assert "semantic_audit_accuracy_not_perfect" in reasons
    assert "semantic_accuracy_mismatch" in reasons


def test_missing_semantic_object_counts_fail_closed():
    audit = _semantic_audit()
    audit.pop("expected_object_count")
    result = evaluate_case([_record(1), _record(2, semantic_audit=audit)])
    assert result["promotable"] is False
    assert "semantic_audit_object_counts_missing" in result["evaluations"][-1]["reasons"]


def test_missing_source_lineage_fails_closed():
    result = evaluate_case([
        _record(1),
        _record(2, source_accepted_iteration=None, source_layout=None),
    ])
    assert result["promotable"] is False
    assert "source_lineage_missing" in result["evaluations"][-1]["reasons"]


def test_incomplete_semantic_iteration_resets_streak():
    records = [
        _record(1),
        _record(2, semantic_audit=_semantic_audit(expected_object_count=8, audited_object_count=7)),
        _record(3),
    ]
    result = evaluate_case(records)
    assert result["promotable"] is False
    assert result["stable_streak"] == 1


def test_visual_native_drift_and_human_approval_are_required():
    for overrides, expected in [
        ({"pixel_fidelity_score": 0.90}, "pixel_fidelity_below_threshold"),
        ({"native_editability_valid": False}, "native_editability_invalid"),
        ({"unauthorized_object_drift_count": 1}, "object_drift_present"),
        ({"human_approved": False}, "human_approval_missing"),
        ({"blocking_count": 1}, "blocking_findings_present"),
    ]:
        result = evaluate_case([_record(1), _record(2, **overrides)])
        assert result["promotable"] is False
        assert expected in result["evaluations"][-1]["reasons"]


def test_bad_middle_iteration_resets_streak():
    records = [_record(1), _record(2, rollback=True), _record(3)]
    result = evaluate_case(records)
    assert result["promotable"] is False
    assert result["stable_streak"] == 1


def test_policy_can_require_three_stable_iterations():
    policy = GoldenPromotionPolicy(min_consecutive_stable_iterations=3)
    assert evaluate_case([_record(1), _record(2)], policy=policy)["promotable"] is False
    assert evaluate_case([_record(1), _record(2), _record(3)], policy=policy)["promotable"] is True


def test_manifest_is_versioned_and_keeps_rollback_pointer_semantic_evidence_and_lineage():
    evaluation = evaluate_case([_record(1), _record(2)])
    previous = {"version": "perfect-first-v1", "case_id": "case-1"}
    manifest = build_promotion_manifest(evaluation=evaluation, previous_golden=previous, version="astra-golden-v3")
    assert manifest["schema"] == "ai-ppt-plus/golden-baseline-manifest/v3"
    assert manifest["immutable"] is True
    assert manifest["version"] == "astra-golden-v3"
    assert manifest["previous_golden"]["version"] == "perfect-first-v1"
    assert manifest["rollback_to_version"] == "perfect-first-v1"
    assert manifest["semantic_evidence"]["semantic_audit_valid"] is True
    assert manifest["semantic_evidence"]["semantic_expected_object_count"] == 8
    assert manifest["semantic_evidence"]["semantic_audited_object_count"] == 8
    assert manifest["source_lineage"]["complete"] is True
    assert manifest["source_lineage"]["source_accepted_iteration"] == 1
    assert manifest["source_lineage"]["source_layout"] == "iteration-1/layout.json"


def test_existing_version_cannot_be_overwritten():
    evaluation = evaluate_case([_record(1), _record(2)])
    try:
        build_promotion_manifest(
            evaluation=evaluation,
            previous_golden={"version": "astra-golden-v3"},
            version="astra-golden-v3",
        )
    except ValueError as exc:
        assert "immutable" in str(exc)
    else:
        raise AssertionError("expected immutable golden version guard")


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("Golden promotion tests passed")
