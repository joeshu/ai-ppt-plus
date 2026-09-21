import importlib.util
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_short_loop_run.py"
spec = importlib.util.spec_from_file_location("short_loop", SCRIPT)
short_loop = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(short_loop)


def _report(tmp_path: Path):
    source = tmp_path / "reference.png"
    pptx = tmp_path / "final.pptx"
    render = tmp_path / "render.png"
    source.write_bytes(b"reference")
    pptx.write_bytes(b"pptx")
    render.write_bytes(b"render")
    phases = {name: True for name in short_loop.PHASES}
    render_sha = short_loop.sha256(render)
    crops = [
        {
            "crop_id": f"c{i}",
            "reference_path": f"ref-{i}.png",
            "candidate_path": f"cand-{i}.png",
            "same_coordinates": True,
            "source_render_sha256": render_sha,
        }
        for i in range(3)
    ]
    return {
        "source": {"path": source.name, "sha256": short_loop.sha256(source)},
        "phases": phases,
        "preflight": {
            "valid": True,
            "checks": {name: "passed" for name in ("package", "source", "runtime", "font", "finalizer")},
        },
        "execution_profile": "fast",
        "performance": {
            "max_repair_rounds": 1,
            "repair_rounds": 1,
            "candidate_build_count": 2,
            "full_render_count": 2,
            "imagegen_retry_counts": {},
            "text_fit_scope": "high_risk",
            "authoritative_visual_renderer": "libreoffice+poppler",
            "artifact_tool_preview_used_for_visual_closeout": False,
        },
        "benchmark": {
            "ttfvr_seconds": 500, "wall_time_seconds": 900,
            "candidate_count": 2, "full_render_count": 2, "imagegen_call_count": 1,
            "native_text_coverage": 1.0, "required_native_coverage": 1.0,
            "whole_slide_raster_count": 0, "material_mismatch_count": 0,
            "protected_regression_count": 0, "reproducible": True,
        },
        "pages": [{"page_id": "slide-1", "material_region_count": 5, "local_crops": crops}],
        "repair_trace": [],
        "visual_closeout_validation": {"valid": True, "status": "passed", "open_text_repair_count": 0},
        "hard_blockers": [],
        "blocking_metrics": {},
        "diagnostics": {"ssim": 0.12, "regional_ssim": 0.2},
        "final": {
            "pptx_path": pptx.name,
            "pptx_sha256": short_loop.sha256(pptx),
            "render_path": render.name,
            "render_sha256": render_sha,
        },
    }


def test_low_visual_metric_is_diagnostic_not_blocker(tmp_path):
    report = _report(tmp_path)
    errors, _ = short_loop.validate(report, tmp_path)
    assert errors == []


def test_visual_metric_cannot_be_promoted_to_production_blocker(tmp_path):
    report = _report(tmp_path)
    report["blocking_metrics"] = {"ssim": 0.9}
    errors, _ = short_loop.validate(report, tmp_path)
    assert any("illegally configured" in error for error in errors)


def test_only_declared_hard_blocker_categories_are_accepted(tmp_path):
    report = _report(tmp_path)
    report["hard_blockers"] = [{"category": "runtime_mirror_mismatch", "active": True}]
    errors, _ = short_loop.validate(report, tmp_path)
    assert any("invalid hard-blocker category" in error for error in errors)


def test_active_real_hard_blocker_fails(tmp_path):
    report = _report(tmp_path)
    report["hard_blockers"] = [{"category": "formal_text_loss", "active": True}]
    errors, _ = short_loop.validate(report, tmp_path)
    assert any("active hard blocker: formal_text_loss" in error for error in errors)


def test_three_local_crops_required_in_fast_profile(tmp_path):
    report = _report(tmp_path)
    report["pages"][0]["local_crops"] = report["pages"][0]["local_crops"][:2]
    errors, _ = short_loop.validate(report, tmp_path)
    assert any("need >= 3" in error for error in errors)


def test_accepted_repair_requires_fresh_after_render(tmp_path):
    report = _report(tmp_path)
    report["repair_trace"] = [{"responsible_object_id": "card-1", "accepted": True}]
    errors, _ = short_loop.validate(report, tmp_path)
    assert any("after-render" in error for error in errors)


def test_failed_visual_closeout_blocks_acceptance(tmp_path):
    report = _report(tmp_path)
    report["visual_closeout_validation"] = {
        "valid": False,
        "status": "failed",
        "open_text_repair_count": 49,
    }
    errors, _ = short_loop.validate(report, tmp_path)
    assert any("visual closeout consistency failed" in error for error in errors)


def test_repair_budget_requires_explicit_exception(tmp_path):
    report = _report(tmp_path)
    report["performance"]["repair_rounds"] = 2
    errors, _ = short_loop.validate(report, tmp_path)
    assert any("repair-round budget exceeded" in error for error in errors)
    report["performance"]["budget_exception_reason"] = "active formal_text_loss blocker"
    errors, _ = short_loop.validate(report, tmp_path)
    assert not any("repair-round budget exceeded" in error for error in errors)


def test_artifact_preview_cannot_close_visual_review(tmp_path):
    report = _report(tmp_path)
    report["performance"]["artifact_tool_preview_used_for_visual_closeout"] = True
    errors, _ = short_loop.validate(report, tmp_path)
    assert any("cannot be visual-closeout authority" in error for error in errors)


def test_duplicate_build_and_render_counts_are_hard_budget_failures(tmp_path):
    report = _report(tmp_path)
    report["performance"]["candidate_build_count"] = 5
    report["performance"]["full_render_count"] = 6
    errors, _ = short_loop.validate(report, tmp_path)
    assert any("candidate-build budget exceeded" in error for error in errors)
    assert any("full-render budget exceeded" in error for error in errors)


if __name__ == "__main__":
    tests = (
        test_low_visual_metric_is_diagnostic_not_blocker,
        test_visual_metric_cannot_be_promoted_to_production_blocker,
        test_only_declared_hard_blocker_categories_are_accepted,
        test_active_real_hard_blocker_fails,
        test_three_local_crops_required_in_fast_profile,
        test_accepted_repair_requires_fresh_after_render,
        test_failed_visual_closeout_blocks_acceptance,
        test_repair_budget_requires_explicit_exception,
        test_artifact_preview_cannot_close_visual_review,
        test_duplicate_build_and_render_counts_are_hard_budget_failures,
    )
    for index, test in enumerate(tests):
        with tempfile.TemporaryDirectory(prefix=f"short-loop-{index}-") as folder:
            test(Path(folder))
    print("short-loop validation tests: ok")
