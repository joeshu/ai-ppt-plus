from __future__ import annotations

import hashlib
import importlib.util
import tempfile
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "evals" / "case-replay-12" / "resolve_generated_assets.py"
spec = importlib.util.spec_from_file_location("resolve_generated_assets", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def _layout():
    return {
        "units": "fraction",
        "slides": [{
            "icons": [{"object_id": "icon", "x": 0.8, "y": 0.1, "w": 0.08, "h": 0.08, "file": "old.png"}],
        }],
    }


def _request():
    return {
        "finding_id": "f1",
        "object_id": "icon",
        "generation_prompt": "matching line icon",
        "background_mode": "transparent",
        "preserve_geometry": {"x": 0.8, "y": 0.1, "w": 0.08, "h": 0.08},
    }


def _asset(path: Path):
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    for x in range(8, 24):
        for y in range(8, 24):
            image.putpixel((x, y), (255, 255, 255, 255))
    image.save(path, format="PNG")


def test_valid_file_but_failed_visual_qa_does_not_resume():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "icon.png"
        _asset(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result = module.resolve_case(
            layout=_layout(),
            requests=[_request()],
            responses={"icon": {"object_id": "icon", "file": str(path), "background_mode": "transparent", "sha256": digest}},
            quality_responses={"icon": {
                "object_id": "icon",
                "approved": True,
                "score": 0.95,
                "structure_score": 0.70,
                "style_score": 0.95,
                "confidence": 0.96,
                "issue_codes": ["silhouette_mismatch"],
                "reasons": ["silhouette differs"],
                "retry_native_generation": True,
            }},
        )
        assert result["report"]["ready"] is False
        assert result["report"]["status"] == "external-asset"
        assert result["report"]["resolved_count"] == 0
        assert result["report"]["quality_rejected"][0]["object_id"] == "icon"
        assert result["report"]["retry_native_generation"][0]["object_id"] == "icon"
        assert result["deck"]["slides"][0]["icons"][0]["file"] == "old.png"


def test_low_confidence_visual_qa_does_not_consume_retry_budget():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "icon.png"
        _asset(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result = module.resolve_case(
            layout=_layout(),
            requests=[_request()],
            responses={"icon": {"object_id": "icon", "file": str(path), "background_mode": "transparent", "sha256": digest}},
            quality_responses={"icon": {
                "object_id": "icon",
                "approved": False,
                "score": 0.70,
                "structure_score": 0.65,
                "style_score": 0.70,
                "confidence": 0.40,
                "issue_codes": ["silhouette_mismatch"],
                "reasons": ["silhouette differs"],
                "retry_native_generation": True,
            }},
        )
        assert result["report"]["ready"] is False
        assert result["report"]["status"] == "external-asset"
        assert result["report"]["resolved_count"] == 0
        assert result["report"]["quality_rejected"][0]["quality"]["confidence"] == 0.40
        assert result["report"]["quality_rejected"][0]["quality"]["retry_native_generation"] is False
        assert result["report"]["retry_native_generation"] == []
        assert result["report"]["user_choice_required"] == []
        assert result["deck"]["slides"][0]["icons"][0]["file"] == "old.png"


def test_visual_qa_approval_allows_binding_and_resume():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "icon.png"
        _asset(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result = module.resolve_case(
            layout=_layout(),
            requests=[_request()],
            responses={"icon": {"object_id": "icon", "file": str(path), "background_mode": "transparent", "sha256": digest}},
            quality_responses={"icon": {
                "object_id": "icon",
                "approved": True,
                "score": 0.95,
                "structure_score": 0.95,
                "style_score": 0.90,
                "confidence": 0.96,
                "issue_codes": [],
                "reasons": [],
                "retry_native_generation": False,
            }},
        )
        assert result["report"]["ready"] is True
        assert result["report"]["status"] == "resume-ready"
        assert result["report"]["resolved_count"] == 1
        assert result["deck"]["slides"][0]["icons"][0]["file"] == str(path.resolve())


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("Asset quality resolution tests passed")
