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
        forbidden = '''if args.reference or args.reference_dir:
            args.require_dual_comparison = True'''
        assert forbidden not in text
