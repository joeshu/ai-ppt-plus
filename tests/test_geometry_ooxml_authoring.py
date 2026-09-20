import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from patch_geometry_ooxml import patch
from validate_geometry_authoring import audit


def make_pptx(path):
    xml = '''<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="1" name="shape-1"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm/><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:sp></p:spTree></p:cSld></p:sld>'''
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", xml)


def test_directional_and_roundrect_geometry_is_native(tmp_path):
    source = tmp_path / "source.pptx"
    output = tmp_path / "output.pptx"
    make_pptx(source)
    resolution = {"schema": "ai-ppt-plus/geometry-primitive-resolution/v2", "valid": True, "repair_required": False, "resolutions": [{"object_id": "shape-1", "page": 1, "primitive": "TRAPEZOID", "parameters": {"direction": "up", "taper_ratio": 0.35}}]}
    patch(source, output, resolution)
    report = audit(resolution, output)
    assert report["valid"] is True, report
    with zipfile.ZipFile(output) as archive:
        xml = archive.read("ppt/slides/slide1.xml").decode()
    assert "custGeom" in xml and "xfrm" in xml and xml.index("xfrm") < xml.index("custGeom")


def test_true_cubic_geometry_is_a_cubic_path(tmp_path):
    source = tmp_path / "source.pptx"
    output = tmp_path / "output.pptx"
    make_pptx(source)
    resolution = {"schema": "ai-ppt-plus/geometry-primitive-resolution/v2", "valid": True, "repair_required": False, "resolutions": [{"object_id": "shape-1", "page": 1, "primitive": "FREEFORM_BEZIER", "parameters": {"control_points": [[0.1, 0.5], [0.2, 0.1], [0.7, 0.1], [0.9, 0.5]]}}]}
    patch(source, output, resolution)
    report = audit(resolution, output)
    assert report["valid"] is True, report
    with zipfile.ZipFile(output) as archive:
        xml = archive.read("ppt/slides/slide1.xml").decode()
    assert xml.count("<a:cubicBezTo") == 1
    assert "<a:lnTo" not in xml


def test_segmented_line_fallback_is_rejected(tmp_path):
    source = tmp_path / "source.pptx"
    output = tmp_path / "output.pptx"
    make_pptx(source)
    resolution = {"schema": "ai-ppt-plus/geometry-primitive-resolution/v2", "valid": True, "repair_required": False, "resolutions": [{"object_id": "shape-1", "page": 1, "primitive": "FREEFORM_BEZIER", "parameters": {"control_points": [[0.1, 0.5], [0.2, 0.1], [0.7, 0.1], [0.9, 0.5]]}}]}
    patch(source, output, resolution)
    with zipfile.ZipFile(output, "r") as archive:
        xml = archive.read("ppt/slides/slide1.xml").decode().replace("<a:cubicBezTo", "<a:lnTo").replace("</a:cubicBezTo>", "</a:lnTo>")
    broken = tmp_path / "broken.pptx"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", xml)
    report = audit(resolution, broken)
    assert report["valid"] is False
    assert any(item["code"] == "geometry_cubic_segmented_line_fallback" for item in report["issues"])


def test_roundrect_preserves_explicit_adjustment(tmp_path):
    source = tmp_path / "source.pptx"
    output = tmp_path / "output.pptx"
    make_pptx(source)
    resolution = {"schema": "ai-ppt-plus/geometry-primitive-resolution/v2", "valid": True, "repair_required": False, "resolutions": [{"object_id": "shape-1", "page": 1, "primitive": "ROUNDRECT", "parameters": {"corner_radius_norm": 0.08}}]}
    patch(source, output, resolution)
    report = audit(resolution, output)
    assert report["valid"] is True, report
    with zipfile.ZipFile(output) as archive:
        xml = archive.read("ppt/slides/slide1.xml").decode()
    assert 'prst="roundRect"' in xml and 'fmla="val 8000"' in xml
