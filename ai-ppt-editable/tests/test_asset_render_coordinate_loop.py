import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "asset_render_coordinate_loop.py"


def run(tmp_path, record):
    p = tmp_path / "records.json"
    p.write_text(json.dumps([record]), encoding="utf-8")
    out = subprocess.run([sys.executable, str(SCRIPT), str(p), "--json"], capture_output=True, text=True)
    return out, json.loads(out.stdout)


def base(observed):
    return {
        "schema":"ai-ppt-plus/asset-render-coordinate/v1",
        "page":1,
        "object_id":"icon-1",
        "asset":{"canvas_px":[100,100],"alpha_bbox_px":[20,20,80,80],"alpha_centroid_px":[50,50],"safe_padding_px":[20,20,20,20]},
        "slot":{"bbox_norm":[0.1,0.1,0.2,0.2]},
        "render":{"canvas_px":[1000,1000],"observed_visible_bbox_px":observed}
    }


def test_exact_projection_has_zero_delta(tmp_path):
    out, report = run(tmp_path, base([140,140,260,260]))
    assert out.returncode == 0
    r = report["records"][0]
    assert r["centroid_delta_px"] == [0.0, 0.0]
    assert r["scale_delta_ratio"] == [0.0, 0.0]
    assert r["repair"]["regenerate_asset"] is False


def test_translation_yields_numeric_repair_without_regeneration(tmp_path):
    out, report = run(tmp_path, base([150,135,270,255]))
    assert out.returncode == 0
    r = report["records"][0]
    assert r["repair"]["classification"] == "placement_only"
    assert r["centroid_delta_px"] == [10.0, -5.0]
    assert r["repair"]["translate_px"] == [-10.0, 5.0]
    assert r["repair"]["regenerate_asset"] is False


def test_scale_error_is_reported_as_ratio(tmp_path):
    out, report = run(tmp_path, base([130,130,270,270]))
    assert out.returncode == 0
    r = report["records"][0]
    assert round(r["scale_delta_ratio"][0], 6) == round(140/120 - 1, 6)
    assert r["repair"]["regenerate_asset"] is False


def test_invalid_record_fails_closed(tmp_path):
    out, report = run(tmp_path, {"object_id":"broken"})
    assert out.returncode == 1
    assert report["valid"] is False
    assert report["records"][0]["issues"][0]["code"] == "coordinate_record_invalid"
