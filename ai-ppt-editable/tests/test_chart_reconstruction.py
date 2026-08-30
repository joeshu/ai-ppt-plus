#!/usr/bin/env python3
"""Regression tests for chart representation and data-evidence gates."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def run(manifest: Path, report: Path, inventory: Path | None = None):
    command = [sys.executable, "scripts/validate_chart_manifest.py", str(manifest), "--require-source", "--report", str(report)]
    if inventory is not None:
        command.extend(["--content-inventory", str(inventory)])
    return subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def base(tmp: Path) -> dict:
    source = tmp / "reference.png"
    source.write_bytes(b"reference")
    categories = ["1月", "2月", "3月"]
    series = [
        {"series_id": "s25", "name": "2025年", "color": "#667A45", "values": [19.65, 18.53, 22.38], "value_labels": [{"category_index": i, "text": str(v)} for i, v in enumerate([19.65, 18.53, 22.38])]},
        {"series_id": "s26", "name": "2026年", "color": "#EAA035", "values": [20.01, 19.47, None], "value_labels": [{"category_index": i, "text": str(v)} for i, v in enumerate([20.01, 19.47])]},
    ]
    chart = {
        "chart_id": "chart-02",
        "slide_no": 1,
        "title": "月度降套用户降收金额（万元）",
        "representation": "static_line_primitives",
        "editability_level": "L2",
        "source_data_status": "unverified",
        "source_data_note": "视觉转录，未提供原始工作簿。",
        "data_source": {"kind": "image_transcription", "authority": "visual_reference", "method": "ocr_plus_human_readback", "source_reference": "reference.png", "source_bbox": [0, 0, 10, 10]},
        "categories": categories,
        "series": series,
        "missing_value_policy": "blank_not_zero",
        "geometry": {"source_bbox": [0, 0, 100, 80], "plot_bbox": [10, 20, 80, 50], "point_anchor_tolerance": 0.015},
        "style": {"line_width_px": 2.2, "marker": "circle", "gridline": "minimal_dashed"},
        "required_elements": ["title", "legend", "category_labels", "data_labels"],
        "visible_elements": {
            "title": [{"object_id": "title", "content": "月度降套用户降收金额（万元）"}],
            "legend": [{"object_id": "l25", "content": "2025年"}, {"object_id": "l26", "content": "2026年"}],
            "category_labels": [{"object_id": f"m{i}", "content": c} for i, c in enumerate(categories)],
            "data_labels": [{"object_id": f"v{i}", "content": str(v)} for i, v in enumerate([19.65, 18.53, 22.38, 20.01, 19.47])],
        },
        "qa": {"reference_region": [0, 0, 100, 80], "status": "pending_human_review"},
    }
    chart["data_snapshot_sha256"] = digest({"kind": "category_chart", "categories": categories, "series": [{"series_id": item["series_id"], "name": item["name"], "values": item["values"]} for item in series]})
    return {"schema": "ai-ppt-plus/chart-reconstruction/v1", "project_id": "fixture", "source_reference": "reference.png", "source_sha256": hashlib.sha256(b"reference").hexdigest(), "coordinate_space": "reference_pixels", "canvas": [100, 80], "charts": [chart]}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="chart-reconstruction-") as temp:
        root = Path(temp)
        manifest = root / "chart-reconstruction.json"
        report = root / "report.json"
        good = base(root)
        manifest.write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")
        result = run(manifest, report)
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(report.read_text(encoding="utf-8"))["valid"] is True

        bad_native = copy.deepcopy(good)
        bad_native["charts"][0]["representation"] = "native_chart"
        manifest.write_text(json.dumps(bad_native, ensure_ascii=False), encoding="utf-8")
        result = run(manifest, report)
        assert result.returncode == 2 and "native_chart_requires_verified_data" in result.stdout, result.stdout

        bad_null = copy.deepcopy(good)
        bad_null["charts"][0]["missing_value_policy"] = "zero_fill"
        manifest.write_text(json.dumps(bad_null, ensure_ascii=False), encoding="utf-8")
        result = run(manifest, report)
        assert result.returncode == 2 and "missing_value_policy_invalid" in result.stdout, result.stdout

        inventory = root / "content-inventory.json"
        inventory.write_text(json.dumps({
            "schema": "ai-ppt-plus/content-inventory/v1",
            "project_id": "fixture",
            "authority": "user_transcription",
            "slides": [{
                "slide_no": 1,
                "charts": [
                    {"chart_id": "chart-02", "representation": "static_line_primitives", "source_data_status": "unverified"},
                    {"chart_id": "chart-03", "representation": "raster_fallback", "source_data_status": "unavailable"},
                ],
            }],
        }, ensure_ascii=False), encoding="utf-8")
        result = run(manifest, report, inventory)
        assert result.returncode == 2 and "chart_manifest_missing_chart" in result.stdout, result.stdout

    print("chart reconstruction evidence gates: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
