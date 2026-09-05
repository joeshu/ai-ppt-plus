from __future__ import annotations

from reconstruction.distillation_record import build_distillation_record, merge_performance_report, summarize_distillation


def _iteration_record():
    return {
        "case_id": "case-1",
        "iteration": 2,
        "status": "rolled-back-regression",
        "accepted": False,
        "resume_after_assets": True,
        "source_resolution": {
            "source": "accepted-state",
            "accepted_iteration": 1,
            "layout": "/tmp/case-1/iteration-1/layout.json",
        },
        "repair_action_count": 2,
        "repair_engine_counts": {"geometry_repair": 1, "asset_repair": 1},
        "pixel_fidelity_score": 0.91,
        "blocking_count": 2,
        "native_editability_valid": True,
        "semantic_accuracy": 1.0,
        "semantic_audit": {
            "valid": True,
            "accuracy": 1.0,
            "error_count": 0,
            "warning_count": 1,
            "expected_object_count": 7,
            "audited_object_count": 7,
        },
        "allowed_object_ids": ["title", "icon"],
        "object_drift": {
            "allowed_object_ids": ["title", "icon"],
            "unauthorized_drift_count": 1,
            "unauthorized_objects": ["body"],
        },
        "regression": {
            "rollback": True,
            "reasons": ["unauthorized_object_drift"],
            "pixel_fidelity_delta": 0.01,
            "blocking_delta": 0,
        },
        "artifacts": {"pptx": "editable.pptx"},
    }


def test_build_record_captures_repair_drift_asset_human_semantic_and_lineage_evidence():
    record = build_distillation_record(
        iteration_record=_iteration_record(),
        asset_resolution={
            "retry_native_generation": [{"object_id": "icon"}],
            "user_choice_required": [{"object_id": "art"}],
            "resolved_count": 1,
        },
        human_approved=False,
    ).to_dict()
    assert record["schema"] == "ai-ppt-plus/astra-distillation-record/v4"
    assert record["case_id"] == "case-1"
    assert record["rollback"] is True
    assert record["source_accepted_iteration"] == 1
    assert record["source_layout"] == "/tmp/case-1/iteration-1/layout.json"
    assert record["unauthorized_object_drift_count"] == 1
    assert record["drift_objects"] == ("body",)
    assert record["asset_retry_count"] == 1
    assert record["asset_user_choice_required_count"] == 1
    assert record["human_approved"] is False
    assert record["semantic_accuracy"] == 1.0
    assert record["semantic_audit"]["valid"] is True
    assert record["semantic_audit"]["expected_object_count"] == 7
    assert record["semantic_audit"]["audited_object_count"] == 7


def test_missing_semantic_audit_and_lineage_are_not_invented():
    source = _iteration_record()
    source.pop("semantic_audit")
    source.pop("semantic_accuracy")
    source.pop("source_resolution")
    record = build_distillation_record(iteration_record=source).to_dict()
    assert record["semantic_accuracy"] is None
    assert record["semantic_audit"] is None
    assert record["source_accepted_iteration"] is None
    assert record["source_layout"] is None


def test_candidate_source_iteration_zero_is_preserved():
    source = _iteration_record()
    source["source_resolution"] = {
        "source": "candidate",
        "accepted_iteration": 0,
        "layout": "/tmp/candidate/layout.json",
    }
    record = build_distillation_record(iteration_record=source).to_dict()
    assert record["source_accepted_iteration"] == 0
    assert record["source_layout"] == "/tmp/candidate/layout.json"


def test_summary_aggregates_without_inventing_missing_scores_or_lineage():
    a = build_distillation_record(iteration_record=_iteration_record()).to_dict()
    second = _iteration_record()
    second.update({"case_id": "case-2", "status": "repaired-needs-qa", "accepted": True, "pixel_fidelity_score": None})
    second["semantic_audit"] = None
    second["semantic_accuracy"] = None
    second.pop("source_resolution")
    second["object_drift"] = {"unauthorized_drift_count": 0, "unauthorized_objects": []}
    second["regression"] = {"rollback": False, "reasons": [], "blocking_delta": -1}
    b = build_distillation_record(iteration_record=second, human_approved=True).to_dict()
    summary = summarize_distillation([a, b])
    assert summary["schema"] == "ai-ppt-plus/astra-distillation-summary/v4"
    assert summary["record_count"] == 2
    assert summary["accepted_count"] == 1
    assert summary["rollback_count"] == 1
    assert summary["human_approved_count"] == 1
    assert summary["mean_pixel_fidelity_score"] == 0.91
    assert summary["semantic_evidence_complete_count"] == 1
    assert summary["source_lineage_complete_count"] == 1


def test_performance_merge_preserves_existing_fields_and_evidence_counts():
    existing = {"schema": "custom/v1", "timing": {"total_seconds": 12.3}, "cache": {"hits": 4}}
    summary = {"record_count": 3, "accepted_count": 2, "rollback_count": 1, "object_drift_rollback_count": 1,
               "asset_retry_count": 2, "asset_user_choice_required_count": 0, "repair_action_count": 5,
               "native_editability_failure_count": 0, "semantic_perfect_count": 2,
               "semantic_evidence_complete_count": 2, "source_lineage_complete_count": 3,
               "mean_pixel_fidelity_score": 0.93, "mean_semantic_accuracy": 1.0}
    merged = merge_performance_report(existing, summary)
    assert merged["schema"] == "custom/v1"
    assert merged["timing"]["total_seconds"] == 12.3
    assert merged["cache"]["hits"] == 4
    assert merged["astra_reconstruction"]["record_count"] == 3
    assert merged["astra_reconstruction"]["rollback_count"] == 1
    assert merged["astra_reconstruction"]["semantic_evidence_complete_count"] == 2
    assert merged["astra_reconstruction"]["source_lineage_complete_count"] == 3


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("Distillation record tests passed")
