from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "evals" / "case-replay-12" / "run_astra_iteration.py"
spec = importlib.util.spec_from_file_location("run_astra_iteration", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def _layout():
    return {
        "units": "fraction",
        "slide_width_in": 13.333,
        "slide_height_in": 7.5,
        "slides": [{
            "texts": [{"object_id": "title", "x": 0.1, "y": 0.1, "w": 0.4, "h": 0.08, "text": "标题", "font_size": 24}],
            "icons": [{"object_id": "icon", "x": 0.8, "y": 0.1, "w": 0.08, "h": 0.08, "file": "icon.png"}],
        }],
    }


def test_prepare_repaired_layout_executes_object_patch_despite_page_diagnostic():
    merged = {
        "version": "1.0",
        "source_id": "reference.png",
        "rendered_id": "render.png",
        "findings": [
            {
                "id": "det-page", "object_id": "slide:1:visual", "domain": "geometry", "severity": "P1",
                "message": "page mismatch", "confidence": 1.0, "proposed_patch": {},
                "evidence": {"source": "dual-comparison", "kind": "pixel", "slide": 1},
            },
            {
                "id": "astra-title", "object_id": "title", "domain": "typography", "severity": "P1",
                "message": "title too small", "confidence": 0.98, "proposed_patch": {"font_size": 27},
            },
        ],
    }
    result = module.prepare_repaired_layout(_layout(), merged)
    assert result["deck"]["slides"][0]["texts"][0]["font_size"] == 27
    assert len(result["report"]["applied"]) == 1
    assert result["report"]["deferred"][0]["diagnostic_only"] is True


def test_prepare_repaired_layout_stops_for_external_asset_generation():
    merged = {
        "version": "1.0",
        "source_id": "reference.png",
        "rendered_id": "render.png",
        "findings": [{
            "id": "astra-icon", "object_id": "icon", "domain": "asset", "severity": "P1",
            "message": "icon style differs", "confidence": 0.98,
            "proposed_patch": {"regenerate": True, "generation_prompt": "matching line icon"},
        }],
    }
    try:
        module.prepare_repaired_layout(_layout(), merged)
    except RuntimeError as exc:
        assert "external asset generation" in str(exc)
    else:
        raise AssertionError("expected external asset boundary to stop deterministic iteration")


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("Astra iteration executor tests passed")
