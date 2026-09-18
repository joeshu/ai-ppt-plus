from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from normalize_layout_fidelity import normalize


def test_16x9_source_is_authored_on_standard_powerpoint_widescreen_canvas():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        layout = root / "layout.json"
        layout.write_text(
            json.dumps({
                "slide_width_px": 1536,
                "slide_height_px": 864,
                "units": "fraction",
                "slides": [{"icons": []}],
            }),
            encoding="utf-8",
        )
        deck, records = normalize(layout)
        assert records == []
        assert deck["ref_width"] == 1536
        assert deck["ref_height"] == 864
        assert deck["slide_width_px"] == 1280.0
        assert deck["slide_height_px"] == 720.0
        assert abs(deck["slide_width_in"] - 13.333333333333334) < 1e-12
        assert deck["slide_height_in"] == 7.5
        assert deck["standard_widescreen_enforced"] is True


def test_non_16x9_source_is_not_silently_resized():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        layout = root / "layout.json"
        layout.write_text(
            json.dumps({
                "slide_width_px": 1024,
                "slide_height_px": 768,
                "units": "fraction",
                "slides": [{"icons": []}],
            }),
            encoding="utf-8",
        )
        deck, _ = normalize(layout)
        assert deck["slide_width_px"] == 1024
        assert deck["slide_height_px"] == 768
        assert deck["standard_widescreen_enforced"] is False


if __name__ == "__main__":
    test_16x9_source_is_authored_on_standard_powerpoint_widescreen_canvas()
    test_non_16x9_source_is_not_silently_resized()
    print("Standard widescreen canvas tests passed")
