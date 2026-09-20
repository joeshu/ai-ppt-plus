import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_geometry_authoring.py"


def make_pptx(path, cubic_count):
    xml = '<p:sld xmlns:p="p" xmlns:a="a">' + ('<a:cubicBezTo></a:cubicBezTo>' * cubic_count) + '</p:sld>'
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ppt/slides/slide1.xml", xml)


def run(tmp_path, expected, actual):
    resolution = {
        "schema": "ai-ppt-plus/geometry-primitive-resolution/v2",
        "resolutions": [
            {"object_id": f"c{i}", "primitive": "FREEFORM_BEZIER"} for i in range(expected)
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
