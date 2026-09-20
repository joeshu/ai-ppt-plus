#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "text_render_feedback.py"
spec = importlib.util.spec_from_file_location("text_render_feedback", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def _render(path: Path, *, shift_x: int = 0, height: int = 20, width: int = 100):
    image = Image.new("RGB", (1000, 500), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((100 + shift_x, 70, 100 + shift_x + width, 70 + height), fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def main():
    with tempfile.TemporaryDirectory(prefix="text-render-feedback-") as raw:
        root = Path(raw)
        reference = root / "reference"
        candidate = root / "candidate"
        _render(reference / "slide-1.png")
        _render(candidate / "slide-1.png", shift_x=12)

        fit = {
            "schema": "ai-ppt-plus/text-fit-deck/v3",
            "slots": [
                {
                    "object_id": "text:title",
                    "slide": 1,
                    "target_pt": 32,
                    "recommended_pt": 32,
                    "geometry_fits": True,
                    "line_topology_preserved": True,
                }
            ],
        }
        plan = {
            "schema": "ai-ppt-plus/authoring-plan/v1",
            "objects": [
                {
                    "object_id": "title",
                    "page": 1,
                    "semantic_role": "title",
                    "implementation_type": "native_text",
                    "bbox": [0.08, 0.08, 0.30, 0.16],
                }
            ],
        }
        report = mod.analyze(
            fit, plan, reference, candidate,
            crop_dir=root / "crops",
            position_tolerance_px=3.0,
            scale_tolerance=0.1,
            coverage_tolerance=0.1,
        )
        assert report["valid"], report
        row = report["records"][0]
        assert row["classification"] == "position_drift", row
        assert row["repair_required"] is True
        assert Path(row["reference"]["crop_path"]).is_file()
        assert Path(row["candidate"]["crop_path"]).is_file()

        _render(candidate / "slide-1.png", height=20, width=100)
        report = mod.analyze(fit, plan, reference, candidate)
        assert report["records"][0]["classification"] == "aligned", report["records"][0]

        _render(candidate / "slide-1.png", height=36, width=100)
        report = mod.analyze(fit, plan, reference, candidate, scale_tolerance=0.1)
        assert report["records"][0]["classification"] == "scale_or_weight_drift", report["records"][0]

        fit["slots"][0]["recommended_pt"] = 20
        report = mod.analyze(fit, plan, reference, candidate)
        assert report["records"][0]["classification"] == "hierarchy_drift", report["records"][0]

        missing = mod.analyze(fit, {"schema": "ai-ppt-plus/authoring-plan/v1", "objects": []}, reference, candidate)
        assert missing["valid"] is False
        assert missing["issues"][0]["code"] == "text_render_owner_unknown"

    print("text render feedback tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
