import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_visual_closeout.py"
spec = importlib.util.spec_from_file_location("visual_closeout", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def fixtures():
    roles = sorted(mod.REQUIRED_REGION_ROLES)
    regions = []
    local_regions = []
    for index, role in enumerate(roles):
        region_id = f"r{index}"
        regions.append({
            "region_id": region_id,
            "role": role,
            "status": "passed",
            "observation": {"reference_features": ["x"], "candidate_features": ["x"], "mismatches": []},
        })
        local_regions.append({"region_id": region_id})
    closeout = {
        "status": "passed",
        "human_visual_review_status": "passed",
        "reference_sha256": "ref",
        "candidate_render_sha256": "render",
        "regions": regions,
        "text_repair_dispositions": [],
        "unresolved_material_mismatches": [],
    }
    local = {"reference_sha256": "ref", "candidate_sha256": "render", "regions": local_regions}
    text = {"records": []}
    return closeout, local, text


def test_consistent_closeout_passes():
    closeout, local, text = fixtures()
    assert mod.validate(closeout, local, text)["valid"] is True


def test_open_text_feedback_blocks_false_pass():
    closeout, local, text = fixtures()
    text["records"] = [{
        "object_id": "title",
        "repair_required": True,
        "candidate": {"render_sha256": "render"},
    }]
    result = mod.validate(closeout, local, text)
    assert result["valid"] is False
    assert any(item["code"] == "text_render_repairs_unclosed" for item in result["issues"])


def test_generic_pass_without_observation_is_rejected():
    closeout, local, text = fixtures()
    closeout["regions"][0].pop("observation")
    result = mod.validate(closeout, local, text)
    assert any(item["code"] == "structured_observation_missing" for item in result["issues"])


def test_open_material_mismatch_blocks_pass():
    closeout, local, text = fixtures()
    closeout["regions"][0]["observation"]["mismatches"] = ["title too large"]
    result = mod.validate(closeout, local, text)
    assert any(item["code"] == "material_visual_mismatch_open" for item in result["issues"])
