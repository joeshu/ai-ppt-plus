#!/usr/bin/env python3
"""Exercise the repository-owned strict Artifact Tool authoring adapter."""
from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "artifact_tool_authoring.mjs"
FONT_DIR = ROOT / "assets" / "fonts"


def json_digest(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    assert SCRIPT.is_file(), SCRIPT
    runtime_node = os.environ.get("CODEX_PRIMARY_RUNTIME_NODE") or shutil.which("node") or shutil.which("node.exe")
    runtime_modules = os.environ.get("CODEX_PRIMARY_RUNTIME_NODE_MODULES")
    if not runtime_node or not runtime_modules or not (Path(runtime_modules) / "@oai" / "artifact-tool").is_dir():
        print("strict Artifact Tool adapter: static contract ok (runtime unavailable; smoke skipped)")
        return 0

    layout = {
        "slide_width_in": 4,
        "slide_height_in": 2.25,
        "theme": {"font": "Noto Sans CJK SC", "text_color": "#111111"},
        "slides": [
            {
                "texts": [{"object_id": "title", "runs": [{"text": "原生", "size": 20}, {"text": "可编辑", "size": 20, "bold": True, "color": "#C00000"}], "x": 0.08, "y": 0.08, "w": 0.84, "h": 0.18, "size": 20}],
                "shapes": [{"object_id": "rule", "type": "line", "x": 0.08, "y": 0.3, "w": 0.84, "h": 0, "line": "#C00000", "line_width": 2}],
                "tables": [{"object_id": "table", "x": 0.08, "y": 0.4, "w": 0.4, "h": 0.35, "rows": [["指标", "值"], ["得分", "90"]], "header_fill": "#FDE9D9", "header_bold": True}],
                "charts": [{"object_id": "chart", "type": "column", "x": 0.54, "y": 0.4, "w": 0.38, "h": 0.5, "categories": ["A", "B"], "series": [{"name": "分数", "values": [90, None]}], "legend": False, "display_blanks_as": "gap", "y_axis": {"min": 50, "max": 100, "majorUnit": 10}}],
                "speaker_notes": "strict adapter smoke",
            }
        ],
    }
    with tempfile.TemporaryDirectory(prefix="artifact-tool-authoring-test-") as raw:
        folder = Path(raw)
        layout_path = folder / "layout.json"
        output = folder / "output.pptx"
        report_path = folder / "report.json"
        inspect_path = folder / "inspect.ndjson"
        layout_path.write_text(json.dumps(layout, ensure_ascii=False), encoding="utf-8")
        command = [
            str(Path(runtime_node).resolve()), str(SCRIPT),
            "--layout", str(layout_path), "--output", str(output),
            "--node-modules", str(Path(runtime_modules).resolve()),
            "--font-dir", str(FONT_DIR.resolve()), "--font-family", "Noto Sans CJK SC",
            "--strict-input", "--report", str(report_path), "--inspect", str(inspect_path),
        ]
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert output.is_file() and output.stat().st_size > 0
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["valid"] is True, report
        assert report["backend"] == "@oai/artifact-tool"
        assert report["package_version"]
        assert report["inspect"]["counts"].get("textbox", 0) >= 1
        assert report["inspect"]["counts"].get("table", 0) >= 1
        assert report["inspect"]["counts"].get("chart", 0) >= 1
        assert len(report["fonts"]) == 4
        with zipfile.ZipFile(output) as package:
            xml = package.read("ppt/slides/slide1.xml")
            chart_xml = package.read("ppt/slides/charts/chart1.xml")
        assert "原生".encode("utf-8") in xml and "可编辑".encode("utf-8") in xml
        assert b"<a:srgbClr val=\"C00000\"" in xml or b"<a:srgbClr val=\"C00000\" />" in xml
        assert b"<a:rPr sz=\"2000\" b=\"1\"" in xml
        assert b"<c:dispBlanksAs val=\"gap\"" in chart_xml
        assert b"<c:min val=\"50\"" in chart_xml and b"<c:max val=\"100\"" in chart_xml

        # Exercise the real worker composer as well.  A manifest-only CJK
        # invocation must register the four concrete faces before the strict
        # adapter is launched; otherwise the preflight could pass while the
        # renderer silently falls back to a system font.
        route_root = folder / "reference-route"
        route_root.mkdir()
        route_layout = dict(layout)
        route_layout["font_manifest"] = str((FONT_DIR / "font-manifest.json").resolve())
        route_layout_path = route_root / "layout.json"
        route_layout_path.write_text(json.dumps(route_layout, ensure_ascii=False), encoding="utf-8")
        (route_root / "route-decision.json").write_text(json.dumps({"route": "reference-reconstruction"}), encoding="utf-8")
        (route_root / "page-graph.json").write_text(json.dumps({"nodes": [{"id": "title", "type": "text", "role": "text"}]}), encoding="utf-8")
        (route_root / "slide-object-manifest.json").write_text(json.dumps({"slides": [{"slide_no": 1, "objects": [{"object_id": "title", "object_type": "editable_text"}]}]}), encoding="utf-8")
        chart_snapshot = {
            "kind": "category_chart",
            "categories": ["A", "B"],
            "series": [{"series_id": "score", "name": "分数", "values": [90, None]}],
        }
        (route_root / "chart-reconstruction.json").write_text(json.dumps({
            "schema": "ai-ppt-plus/chart-reconstruction/v1",
            "project_id": "artifact-tool-smoke",
            "coordinate_space": "reference_pixels",
            "canvas": [100, 80],
            "charts": [{
                "chart_id": "chart",
                "slide_no": 1,
                "representation": "native_chart",
                "editability_level": "L1",
                "source_data_status": "verified",
                "data_source": {"kind": "inline_fixture", "authority": "test", "method": "deterministic_smoke"},
                "categories": ["A", "B"],
                "series": [{"series_id": "score", "name": "分数", "values": [90, None]}],
                "missing_value_policy": "blank_not_zero",
                "data_snapshot_sha256": json_digest(chart_snapshot),
                "required_elements": ["category_labels"],
                "visible_elements": {"category_labels": [{"object_id": "category-a", "content": "A"}, {"object_id": "category-b", "content": "B"}]},
                "geometry": {"source_bbox": [0, 0, 100, 80], "plot_bbox": [10, 20, 80, 50], "point_anchor_tolerance": 0.02},
                "qa": {"reference_region": [0, 0, 100, 80]},
            }],
        }, ensure_ascii=False), encoding="utf-8")
        route_output = route_root / "route-output.pptx"
        route_command = [
            os.environ.get("PYTHON", os.sys.executable), str(ROOT / "scripts" / "compose_pptx.py"),
            str(route_layout_path), str(route_output), "--authoring-backend", "artifact-tool",
            "--node", str(Path(runtime_node).resolve()), "--node-modules", str(Path(runtime_modules).resolve()),
            "--font-manifest", str((FONT_DIR / "font-manifest.json").resolve()), "--strict-input",
        ]
        route_result = subprocess.run(route_command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert route_result.returncode == 0, route_result.stdout + route_result.stderr
        route_report = json.loads(route_output.with_name("route-output.artifact-tool.json").read_text(encoding="utf-8"))
        assert route_report["backend"] == "@oai/artifact-tool"
        assert len(route_report["fonts"]) == 4
    print("strict Artifact Tool adapter: smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
