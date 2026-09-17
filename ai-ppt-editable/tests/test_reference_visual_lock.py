from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from normalize_layout_fidelity import normalize


def test_reference_visual_bbox_lock_places_visible_alpha_subject_exactly():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        asset = Image.new("RGBA", (80, 60), (0, 0, 0, 0))
        ImageDraw.Draw(asset).rectangle((10, 10, 49, 39), fill=(220, 0, 0, 255))
        asset.save(root / "icon.png")
        layout = root / "layout.json"
        layout.write_text(json.dumps({
            "units": "px", "ref_width": 1536, "ref_height": 864,
            "assets_dir": str(root), "strict_input": True,
            "slides": [{"icons": [{
                "object_id": "card1-icon", "file": "icon.png",
                "x": 0, "y": 0, "w": 100, "h": 100,
                "placement_mode": "alpha-centroid-fit",
                "reference_visual_bbox_px": [200, 300, 80, 60],
            }]}],
        }), encoding="utf-8")
        deck, records = normalize(layout)
        assert len(records) == 1
        record = records[0]
        assert record["mode"] == "reference_visual_lock"
        assert record["placed_visible_bbox_px"] == [200.0, 300.0, 80.0, 60.0]
        assert deck["slides"][0]["icons"][0]["visual_lock_applied"] is True


def test_reference_visual_centroid_overrides_bbox_center():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        asset = Image.new("RGBA", (80, 60), (0, 0, 0, 0))
        ImageDraw.Draw(asset).rectangle((5, 10, 44, 39), fill=(220, 0, 0, 255))
        asset.save(root / "icon.png")
        layout = root / "layout.json"
        layout.write_text(json.dumps({
            "units": "px", "ref_width": 1536, "ref_height": 864,
            "assets_dir": str(root), "strict_input": True,
            "slides": [{"icons": [{
                "object_id": "card1-icon", "file": "icon.png",
                "x": 0, "y": 0, "w": 100, "h": 100,
                "reference_visual_bbox_px": [200, 300, 80, 60],
                "reference_visual_centroid_px": [245, 335],
            }]}],
        }), encoding="utf-8")
        _, records = normalize(layout)
        record = records[0]
        assert record["alignment"] == "reference_visual_centroid"
        placed = record["placed_canvas_px"]
        geom = record["alpha_geometry"]
        scale = record["scale"]
        cx = placed[0] + geom["centroid_x"] * scale
        cy = placed[1] + geom["centroid_y"] * scale
        assert abs(cx - 245) < 1e-6
        assert abs(cy - 335) < 1e-6


if __name__ == "__main__":
    test_reference_visual_bbox_lock_places_visible_alpha_subject_exactly()
    test_reference_visual_centroid_overrides_bbox_center()
    print("Reference visual lock tests passed")
