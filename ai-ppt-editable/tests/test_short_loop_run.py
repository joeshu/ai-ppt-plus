import importlib.util
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
    crops = [
        {
            "crop_id": f"c{i}",
            "reference_path": f"ref-{i}.png",
            "candidate_path": f"cand-{i}.png",
            "same_coordinates": True,
        }
        for i in range(5)
    ]
    return {
        "source": {"path": source.name, "sha256": short_loop.sha256(source)},
        "phases": phases,
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
            "render_sha256": short_loop.sha256(render),
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


def test_five_local_crops_required_when_five_material_regions_exist(tmp_path):
    report = _report(tmp_path)
    report["pages"][0]["local_crops"] = report["pages"][0]["local_crops"][:4]
    errors, _ = short_loop.validate(report, tmp_path)
    assert any("need >= 5" in error for error in errors)


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
