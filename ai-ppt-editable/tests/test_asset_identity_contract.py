import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATE = ROOT / "scripts" / "validate_asset_identity_contracts.py"
BUILD = ROOT / "scripts" / "build_imagegen_asset_jobs.py"


def contract():
    return {
        "schema": "ai-ppt-plus/asset-identity-contract/v1",
        "semantic_identity": {
            "subject": "red upward growth arrow",
            "must_preserve": ["single rising arrow", "broad filled body"],
            "forbidden_substitutions": ["thin line arrow", "generic chevron"]
        },
        "contour_traits": ["wide tail", "pointed upper-right head"],
        "color_roles": [{"role": "primary", "hex": "#E60012"}],
        "alpha": {"required": True, "transparent_edges": True, "safe_padding_ratio": 0.08},
        "provenance": {"generation_required": True, "source_crop_final_fallback": False, "reference_sha256": "a"*64}
    }


def plan(c=None):
    return {
        "schema": "ai-ppt-plus/authoring-plan/v1",
        "source": {"sha256": "a"*64, "width_px": 1672, "height_px": 941},
        "canvas": {"width": 1, "height": 1, "units": "normalized"},
        "objects": [{
            "object_id": "growth-arrow", "page": 1, "semantic_role": "growth-arrow",
            "implementation_type": "imagegen_asset", "bbox": [0.2,0.2,0.3,0.2],
            "z_role": "content", "asset_contract": c if c is not None else contract()
        }]
    }


def test_valid_contract_passes(tmp_path):
    p = tmp_path / "plan.json"; p.write_text(json.dumps(plan()), encoding="utf-8")
    run = subprocess.run([sys.executable, str(VALIDATE), str(p), "--json"], capture_output=True, text=True)
    assert run.returncode == 0
    assert json.loads(run.stdout)["valid"] is True


def test_generic_identity_is_blocked(tmp_path):
    c = contract(); c["semantic_identity"]["must_preserve"] = []
    p = tmp_path / "plan.json"; p.write_text(json.dumps(plan(c)), encoding="utf-8")
    run = subprocess.run([sys.executable, str(VALIDATE), str(p), "--json"], capture_output=True, text=True)
    report = json.loads(run.stdout)
    assert run.returncode == 1
    assert any(x["code"] == "asset_identity_traits_missing" for x in report["issues"])


def test_color_and_provenance_are_blocked(tmp_path):
    c = contract(); c["color_roles"][0]["hex"] = "red"; c["provenance"]["source_crop_final_fallback"] = True
    p = tmp_path / "plan.json"; p.write_text(json.dumps(plan(c)), encoding="utf-8")
    run = subprocess.run([sys.executable, str(VALIDATE), str(p), "--json"], capture_output=True, text=True)
    codes = {x["code"] for x in json.loads(run.stdout)["issues"]}
    assert "asset_color_hex_invalid" in codes
    assert "asset_provenance_contract_invalid" in codes


def test_imagegen_job_cache_key_and_prompt_include_contract(tmp_path):
    base = {
        "source": {"sha256": "a"*64},
        "assets": [{
            "asset_id": "growth-arrow", "asset_class": "icon", "route": "imagegen_asset",
            "source_bbox": [0.2,0.2,0.3,0.2], "prompt": "recreate the reference asset",
            "asset_contract": contract()
        }]
    }
    inp = tmp_path / "assets.json"; out = tmp_path / "jobs.json"
    inp.write_text(json.dumps(base), encoding="utf-8")
    run = subprocess.run([sys.executable, str(BUILD), str(inp), "--output", str(out)], capture_output=True, text=True)
    assert run.returncode == 0
    first = json.loads(out.read_text(encoding="utf-8"))["jobs"][0]
    assert first["contract_complete"] is True
    assert "primary=#E60012" in first["request"]["generation_prompt"]
    assert first["retry"]["placement_only_consumes_generation_attempt"] is False
    key1 = first["cache_key"]
    base["assets"][0]["asset_contract"]["color_roles"][0]["hex"] = "#CC0010"
    inp.write_text(json.dumps(base), encoding="utf-8")
    subprocess.run([sys.executable, str(BUILD), str(inp), "--output", str(out)], check=True, capture_output=True, text=True)
    key2 = json.loads(out.read_text(encoding="utf-8"))["jobs"][0]["cache_key"]
    assert key1 != key2
