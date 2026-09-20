import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_geometry_authoring.py"
sys.path.insert(0, str(ROOT / "scripts"))
from geometry_authoring import validate_artifact_tool_binding  # noqa: E402


def make_pptx(path, cubic_count):
    xml = '<p:sld xmlns:p="p" xmlns:a="a">' + ('<a:cubicBezTo></a:cubicBezTo>' * cubic_count) + '</p:sld>'
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ppt/slides/slide1.xml", xml)


def run(tmp_path, expected, actual):
    resolution = {
        "schema": "ai-ppt-plus/geometry-primitive-resolution/v2",
        "resolutions": [
            {"object_id": f"c{i}", "page": 1, "primitive": "FREEFORM_BEZIER", "parameters": {"control_points": [[0.1, 0.5], [0.2, 0.1], [0.7, 0.1], [0.9, 0.5]]}} for i in range(expected)
        ],
    }
    rp = tmp_path / "geometry-resolution.json"
    pp = tmp_path / "candidate.pptx"
    rp.write_text(json.dumps(resolution), encoding="utf-8")
    make_pptx(pp, actual)
    out = subprocess.run([sys.executable, str(SCRIPT), str(rp), str(pp), "--json"], capture_output=True, text=True)
    return out, json.loads(out.stdout)


def test_cubic_bezier_ooxml_passes(tmp_path):
    out, report = run(tmp_path, 2, 2)
    assert out.returncode == 0
    assert report["valid"] is True


def test_segmented_curve_without_cubic_is_blocked(tmp_path):
    out, report = run(tmp_path, 1, 0)
    assert out.returncode == 1
    assert any(x["code"] == "geometry_cubic_bezier_missing_in_ooxml" for x in report["issues"])


def test_artifact_tool_binding_is_page_and_object_bound():
    deck = {"slides": [{"shapes": [{"object_id": "page-1"}]}, {"shapes": [{"object_id": "page-2"}]}]}
    resolution = {"resolutions": [{"object_id": "page-2", "page": 2, "primitive": "ROUNDRECT", "parameters": {"corner_radius_norm": 0.1}}]}
    report = validate_artifact_tool_binding(deck, resolution)
    assert report["valid"] is True
    assert report["targets"][0]["page"] == 2


def test_artifact_tool_binding_blocks_missing_target():
    deck = {"slides": [{"shapes": []}]}
    resolution = {"resolutions": [{"object_id": "missing", "page": 1, "primitive": "TRAPEZOID", "parameters": {}}]}
    report = validate_artifact_tool_binding(deck, resolution)
    assert report["valid"] is False
    assert any(item["code"] == "geometry_binding_target_missing" for item in report["issues"])
