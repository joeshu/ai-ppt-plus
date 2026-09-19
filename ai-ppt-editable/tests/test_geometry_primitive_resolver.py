import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "resolve_geometry_primitives.py"


def run(tmp_path, objects):
    plan = {
        "schema": "ai-ppt-plus/authoring-plan/v1",
        "source": {"sha256": "0"*64, "width_px": 1536, "height_px": 864},
        "canvas": {"width": 1, "height": 1, "units": "normalized"},
        "objects": objects,
    }
    p = tmp_path / "authoring-plan.json"
    p.write_text(json.dumps(plan), encoding="utf-8")
    out = subprocess.run([sys.executable, str(SCRIPT), str(p), "--json"], capture_output=True, text=True)
    return out, json.loads(out.stdout)


def obj(object_id, impl, role, geometry):
    return {
        "object_id": object_id, "page": 1, "semantic_role": role,
        "implementation_type": impl, "bbox": [0.1, 0.1, 0.2, 0.1],
        "z_role": "content", "geometry_contract": geometry,
    }


def test_filled_arrow_is_not_connector(tmp_path):
    out, report = run(tmp_path, [obj("a", "native_shape", "process arrow", {"filled_body": True, "shaft": True, "arrowhead": True})])
    assert out.returncode == 0
    assert report["resolutions"][0]["primitive"] == "FILLED_ARROW"
    assert report["repair_required"] is False


def test_curved_path_requires_freeform_bezier(tmp_path):
    out, report = run(tmp_path, [obj("curve", "connector", "timeline curve", {"requires_cubic_bezier": True})])
    assert out.returncode == 0
    r = report["resolutions"][0]
    assert r["primitive"] == "FREEFORM_BEZIER"
    assert r["expected_implementation_type"] == "freeform"
    assert report["repair_required"] is True


def test_stroke_only_two_endpoint_path_is_connector(tmp_path):
    out, report = run(tmp_path, [obj("line", "connector", "connector", {"stroke_only": True, "endpoints": [[0, 0], [1, 1]]})])
    assert out.returncode == 0
    assert report["resolutions"][0]["primitive"] == "CONNECTOR"


def test_complex_art_routes_to_imagegen_asset(tmp_path):
    out, report = run(tmp_path, [obj("art", "native_shape", "large artistic rise arrow", {"complex_art": True, "gradient_3d": True})])
    assert out.returncode == 0
    assert report["resolutions"][0]["primitive"] == "IMAGEGEN_COMPLEX"
    assert report["repair_required"] is True


def test_invalid_explicit_hint_blocks(tmp_path):
    out, report = run(tmp_path, [obj("x", "native_shape", "shape", {"primitive_hint": "MAGIC"})])
    assert out.returncode == 1
    assert any(x["code"] == "geometry_primitive_unresolved" for x in report["issues"])
