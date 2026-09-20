#!/usr/bin/env python3
"""B5 coordinate projection, RGBA binding and final crop evidence tests."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "asset_render_coordinate_loop.py"


def _asset(path: str | None = None) -> dict:
    value = {
        "canvas_px": [100, 100],
        "alpha_bbox_px": [20, 20, 80, 80],
        "alpha_centroid_px": [50, 50],
        "safe_padding_px": [20, 20, 20, 20],
    }
    if path:
        value = {"path": path}
    return value


def _record(observed: list[float], asset: dict | None = None) -> dict:
    return {
        "schema": "ai-ppt-plus/asset-render-coordinate/v1",
        "page": 1,
        "object_id": "icon-1",
        "asset": asset or _asset(),
        "slot": {"bbox_norm": [0.1, 0.1, 0.2, 0.2]},
        "render": {"canvas_px": [1000, 1000], "observed_visible_bbox_px": observed},
    }


def _run(tmp: Path, record: dict, *extra: str) -> tuple[subprocess.CompletedProcess[str], dict]:
    source = tmp / "records.json"
    source.write_text(json.dumps([record]), encoding="utf-8")
    completed = subprocess.run([sys.executable, str(SCRIPT), str(source), "--json", *extra], capture_output=True, text=True, check=False)
    return completed, json.loads(completed.stdout)


def test_projection_and_translation_delta() -> None:
    with tempfile.TemporaryDirectory(prefix="b5-coordinate-") as folder:
        completed, report = _run(Path(folder), _record([150, 135, 270, 255]))
        assert completed.returncode == 0, completed.stderr
        result = report["records"][0]
        assert result["repair"]["classification"] == "placement_only"
        assert result["centroid_delta_px"] is None
        assert result["bbox_center_delta_px"] == [10.0, -5.0]
        assert result["repair"]["translate_px"] == [-10.0, 5.0]
        assert result["repair"]["translation_basis"] == "visible_bbox_center"
        assert result["repair"]["regenerate_asset"] is False
        assert report["repair_loop_required"] is True


def test_auto_binds_rgba_and_captures_fresh_render_crop() -> None:
    with tempfile.TemporaryDirectory(prefix="b5-coordinate-qa-") as folder:
        root = Path(folder)
        from PIL import Image

        asset = root / "icon.png"
        image = Image.new("RGBA", (100, 80), (0, 0, 0, 0))
        for x in range(20, 80):
            for y in range(10, 70):
                image.putpixel((x, y), (255, 0, 0, 255))
        image.save(asset)
        render_dir = root / "rendered"
        render_dir.mkdir()
        Image.new("RGB", (1000, 1000), "white").save(render_dir / "slide-1.png")
        record = _record([140, 140, 260, 260], _asset("icon.png"))
        record["render"]["path"] = str(root / "stale-render.png")
        completed, report = _run(
            root,
            record,
            "--base-dir", str(root),
            "--render-dir", str(render_dir),
            "--capture-crops", str(root / "crops"),
            "--auto-bind-asset-qa",
            "--require-render-evidence",
            "--require-crop-evidence",
        )
        assert completed.returncode == 0, completed.stderr
        result = report["records"][0]
        assert result["asset"]["qa_binding"]["status"] == "computed"
        assert result["asset"]["alpha_bbox_px"] == [20, 10, 80, 70]
        assert result["asset"]["aspect_ratio"] == 1.25
        assert result["asset"]["visible_aspect_ratio"] == 1.0
        assert result["render_evidence"]["crop_path"]
        assert Path(result["render_evidence"]["crop_path"]).is_file()
        assert report["asset_qa_bound_count"] == 1
        assert report["render_crop_evidence_count"] == 1


def test_invalid_record_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="b5-coordinate-invalid-") as folder:
        completed, report = _run(Path(folder), {"object_id": "broken"})
        assert completed.returncode == 1
        assert report["valid"] is False
        assert report["records"][0]["issues"][-1]["code"] == "coordinate_record_invalid"


def test_explicit_observed_centroid_is_not_confused_with_bbox_center() -> None:
    with tempfile.TemporaryDirectory(prefix="b5-coordinate-centroid-") as folder:
        record = _record([140, 140, 260, 260])
        record["render"]["observed_visual_centroid_px"] = [215, 185]
        completed, report = _run(Path(folder), record)
        assert completed.returncode == 0, completed.stderr
        result = report["records"][0]
        assert result["bbox_center_delta_px"] == [0.0, 0.0]
        assert result["centroid_delta_px"] == [15.0, -15.0]
        assert result["repair"]["translation_basis"] == "observed_visual_centroid"


def test_missing_explicit_render_path_fails_closed_when_required() -> None:
    with tempfile.TemporaryDirectory(prefix="b5-coordinate-render-missing-") as folder:
        root = Path(folder)
        record = _record([140, 140, 260, 260])
        record["render"]["path"] = str(root / "missing.png")
        completed, report = _run(root, record, "--require-render-evidence")
        assert completed.returncode == 1
        assert any(item["code"] == "render_evidence_missing" for item in report["records"][0]["issues"])


def test_required_inventory_cannot_be_empty() -> None:
    with tempfile.TemporaryDirectory(prefix="b5-coordinate-empty-") as folder:
        root = Path(folder)
        source = root / "records.json"
        source.write_text("[]", encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), str(source), "--json", "--require-records"],
            capture_output=True, text=True, check=False,
        )
        report = json.loads(completed.stdout)
        assert completed.returncode == 1
        assert report["issues"] == [{"code": "coordinate_records_missing"}]


if __name__ == "__main__":
    test_projection_and_translation_delta()
    test_auto_binds_rgba_and_captures_fresh_render_crop()
    test_invalid_record_fails_closed()
    test_missing_explicit_render_path_fails_closed_when_required()
    test_required_inventory_cannot_be_empty()
    print("B5 coordinate loop tests passed")
