#!/usr/bin/env python3
"""Executable B4 resolver, binding and OOXML contract regression."""
from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from geometry_authoring import validate_artifact_tool_binding  # noqa: E402
from patch_geometry_ooxml import patch  # noqa: E402
from resolve_geometry_primitives import resolve  # noqa: E402
from validate_geometry_authoring import audit  # noqa: E402


def make_pptx(path: Path) -> None:
    xml = '''<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="1" name="group/shape-1"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm/><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:sp></p:spTree></p:cSld></p:sld>'''
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", xml)


def plan_for(geometry: dict, implementation: str = "native_shape", role: str = "shape") -> dict:
    return {
        "schema": "ai-ppt-plus/authoring-plan/v1",
        "objects": [{
            "object_id": "shape-1", "page": 1, "semantic_role": role,
            "implementation_type": implementation, "geometry_contract": geometry,
        }],
    }


def main() -> int:
    valid_curve = resolve(plan_for({
        "requires_cubic_bezier": True,
        "control_points": [[0.1, 0.5], [0.2, 0.1], [0.7, 0.1], [0.9, 0.5]],
    }, implementation="freeform", role="curve"))
    assert valid_curve["valid"] is True, valid_curve
    assert valid_curve["resolutions"][0]["page"] == 1

    invalid_direction = resolve(plan_for({"trapezoid": True, "direction": "diagonal"}))
    assert invalid_direction["valid"] is False
    assert any(item["code"] == "geometry_direction_invalid" for item in invalid_direction["issues"])

    missing_controls = resolve(plan_for({"requires_cubic_bezier": True}, implementation="freeform", role="curve"))
    assert missing_controls["valid"] is False
    assert any(item["code"] == "geometry_cubic_control_points_missing" for item in missing_controls["issues"])

    binding = validate_artifact_tool_binding(
        {"slides": [{"shapes": [{"object_id": "shape-1"}]}]},
        {"resolutions": [{"object_id": "shape-1", "page": 1, "primitive": "ROUNDRECT", "parameters": {"corner_radius_norm": 0.1}}]},
    )
    assert binding["valid"] is True and binding["target_count"] == 1, binding

    with tempfile.TemporaryDirectory(prefix="geometry-b4-contract-") as raw:
        folder = Path(raw)
        source = folder / "source.pptx"
        output = folder / "output.pptx"
        make_pptx(source)
        resolution = {
            "schema": "ai-ppt-plus/geometry-primitive-resolution/v2",
            "valid": True,
            "repair_required": False,
            "resolutions": [{
                "object_id": "shape-1", "page": 1, "primitive": "FREEFORM_BEZIER",
                "parameters": {"control_points": [[0.1, 0.5], [0.2, 0.1], [0.7, 0.1], [0.9, 0.5]]},
            }],
        }
        patch(source, output, resolution)
        report = audit(resolution, output)
        assert report["valid"] is True, report
        with zipfile.ZipFile(output, "r") as archive:
            xml = archive.read("ppt/slides/slide1.xml").decode()
        assert xml.count("<a:cubicBezTo") == 1 and "<a:lnTo" not in xml

        broken = folder / "broken.pptx"
        broken_xml = xml.replace("<a:cubicBezTo", "<a:lnTo").replace("</a:cubicBezTo>", "</a:lnTo>")
        with zipfile.ZipFile(broken, "w") as archive:
            archive.writestr("ppt/slides/slide1.xml", broken_xml)
        broken_report = audit(resolution, broken)
        assert broken_report["valid"] is False
        assert any(item["code"] == "geometry_cubic_segmented_line_fallback" for item in broken_report["issues"])

    print("B4 geometry contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
