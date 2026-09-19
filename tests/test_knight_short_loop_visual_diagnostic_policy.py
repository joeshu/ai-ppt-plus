from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_delivery_check_has_no_default_reference_fidelity_gate():
    for path in ("scripts/delivery_check.py", "ai-ppt-editable/scripts/delivery_check.py"):
        text = read(path)
        assert 'default=0.90' not in text
        assert 'reference_fidelity_below_threshold' not in text
        assert 'reference_layout_fidelity_below_threshold' not in text
        assert '"diagnostic_only": True' in text
        assert '"repair_loop_required": visual_comparison_report.get("valid") is not True' in text


def test_project_validation_treats_visual_reports_as_repair_signals():
    for path in ("scripts/validate_project.py", "ai-ppt-editable/scripts/validate_project.py"):
        text = read(path)
        assert 'diagnostic_only=True' in text
        assert '"repair_signals"' in text
        assert '"repair_loop_required": visual_comparison.get("valid") is not True' in text


def test_pipeline_does_not_forward_visual_threshold_as_production_gate():
    for path in ("scripts/run_pipeline.py", "ai-ppt-editable/scripts/run_pipeline.py"):
        text = read(path)
        assert 'comparison_args.extend(["--min-reference-fidelity", str(args.visual_threshold)])' not in text
        assert 'comparison_args.extend(["--threshold", str(args.visual_threshold)])' not in text
        assert 'comparison_args.append("--strict")' not in text
        assert "release never auto-requires it" in text


def test_external_dual_compare_is_not_auto_required_for_release():
    for path in ("scripts/run_pipeline.py", "ai-ppt-editable/scripts/run_pipeline.py"):
        text = read(path)
        forbidden = '''if args.reference or args.reference_dir:\n            args.require_dual_comparison = True'''
        assert forbidden not in text


def test_aggregate_converts_visual_failures_to_repair_signals():
    for path in ("scripts/aggregate_project_reports.py", "ai-ppt-editable/scripts/aggregate_project_reports.py"):
        text = read(path)
        assert "VISUAL_DIAGNOSTIC_REPORT_TYPES" in text
        assert '"visual_diagnostic_requires_repair"' in text
        assert '"repair_loop_required": repair_loop_required' in text
        assert '"production_state": production_state' in text
        assert '"next_state": production_state' in text


def test_report_bundle_excludes_visual_diagnostics_from_hard_technical_failures():
    for path in ("scripts/validate_report_bundle.py", "ai-ppt-editable/scripts/validate_report_bundle.py"):
        text = read(path)
        assert "VISUAL_DIAGNOSTIC_STEPS" in text
        assert "actual_failed - NON_TECHNICAL_STEPS - VISUAL_DIAGNOSTIC_STEPS" in text
        assert '"diagnostic_failure_requires_repair_state"' in text
        assert '"release_requires_repair_complete"' in text
        assert '"production_state": expected_production_state' in text


def test_pipeline_exposes_only_three_short_loop_production_states():
    for path in ("scripts/run_pipeline.py", "ai-ppt-editable/scripts/run_pipeline.py"):
        text = read(path)
        assert '"hard-correctness-fail"' in text
        assert '"repair-required"' in text
        assert '"final-pptx-ready"' in text
        assert "and step[\"name\"] not in VISUAL_DIAGNOSTIC_STEPS" in text
        assert "and not repair_loop_required" in text


def test_numeric_quality_score_is_diagnostic_only():
    for path in ("scripts/delivery_check.py", "ai-ppt-editable/scripts/delivery_check.py"):
        text = read(path)
        assert "quality_threshold_not_met" not in text
        assert '"declared_quality_score"' in text
        assert '"diagnostic_only": True' in text
    for path in ("scripts/run_pipeline.py", "ai-ppt-editable/scripts/run_pipeline.py"):
        text = read(path)
        assert 'missing.append("--quality-score")' not in text
        assert 'optional diagnostic quality score' in text


def test_preview_similarity_threshold_is_repair_signal_only():
    for path in ("scripts/validate_preview_consistency.py", "ai-ppt-editable/scripts/validate_preview_consistency.py"):
        text = read(path)
        assert '"threshold_diagnostic_only": True' in text
        assert '"repair_loop_required": bool(repair_signals)' in text
        assert '"severity": "warning", "code": "preview_threshold_not_met"' in text
        assert '"severity": "blocker", "code": "preview_threshold_not_met"' not in text


def test_hard_region_scalar_thresholds_are_repair_diagnostics():
    text = read("ai-ppt-editable/scripts/hard_region_crop_gate.py")
    assert '"gate_mode": "repair_diagnostic"' in text
    assert '"repair_loop_required": bool(diagnostic_failures)' in text
    assert '"absolute_threshold_applied": False' in text
    assert '"diagnostic_only": True' in text


def test_visual_lock_scores_and_typography_deltas_are_repair_signals():
    text = read("ai-ppt-editable/scripts/validate_visual_lock.py")
    assert '"repair_loop_required": bool(repair_signals)' in text
    assert '"critical_region_score_below_95"' in text
    assert '"typography_delta_over_12_percent"' in text
    assert '"diagnostic_only": True' in text
    assert 'fail(f"{rid}:critical_region_score_below_95"' not in text
    assert 'fail(f"{rid}:typography_delta_over_12_percent"' not in text
