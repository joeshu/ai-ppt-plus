#!/usr/bin/env python3
"""Regression tests for native canvas negotiation and manifest path handling."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))

from validate_visual_generation_plan import (  # noqa: E402
    resolve_cli_path,
    sha256,
    validate_evidence,
)


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="native-canvas-") as temp:
        root = Path(temp)
        visual = root / "visual"
        slides = visual / "slides"
        slides.mkdir(parents=True)
        prompt = visual / "prompt.md"
        prompt.write_text("native canvas fixture\n", encoding="utf-8")

        source = root / "generated.png"
        copied = slides / "slide.png"
        image = Image.new("RGB", (1672, 941), "white")
        image.save(source)
        image.save(copied)

        plan = {
            "project_id": "native-canvas-fixture",
            "mode": "image-slide",
            "generation_contract": {
                "skill": "ai-ppt-visual-gen",
                "tool_resolution": "runtime-discovery",
                "backend_policy": "raster-only",
                "source_retention": "generated-source-and-project-copy",
                "no_code_overlay": True,
            },
            "generation_session": {
                "session_id": "native-canvas-test",
                "continuity_policy": "single-model-single-context",
            },
            "canvas": {"ratio": "16:9", "width_px": 2048, "height_px": 1152},
            "canvas_policy": {
                "require_exact_dimensions": False,
                "minimum_width_px": 1600,
                "minimum_height_px": 900,
                "on_mismatch": "warn",
            },
            "slides": [{
                "slide_no": 1,
                "prompt_file": "prompt.md",
                "production_prompt": "",
                "formal_text": [],
            }],
        }
        plan_path = visual / "plan.json"
        write_json(plan_path, plan)
        manifest = {
            "schema": "ai-ppt-plus/visual-generation-manifest/v1",
            "project_id": "native-canvas-fixture",
            "plan_sha256": sha256(plan_path),
            "generator_skill": "ai-ppt-visual-gen",
            "tool_resolution": "runtime-discovery",
            "backend_policy": "raster-only",
            "source_retention": "generated-source-and-project-copy",
            "no_code_overlay": True,
            "generation_session_id": "native-canvas-test",
            "continuity_policy": "single-model-single-context",
            "slides": [{
                "slide_no": 1,
                "prompt_file": "prompt.md",
                "prompt_sha256": sha256(prompt),
                "generated_source": str(source),
                "copied_to": "slides/slide.png",
                "generated_source_sha256": sha256(source),
                "copied_to_sha256": sha256(copied),
                "backend": "codex-imagegen",
                "model_or_tool": "Codex built-in image_gen",
                "generation_session_id": "native-canvas-test",
                "context_continuity_status": "preserved",
                "canvas": {"width_px": 1672, "height_px": 941, "ratio": "16:9"},
            }],
        }
        manifest_path = visual / "manifest.json"
        write_json(manifest_path, manifest)

        issues: list[dict] = []
        validate_evidence(plan_path, plan, manifest_path, issues, False)
        codes = [item.get("code") for item in issues]
        assert codes.count("generation_image_native_resolution") == 2, issues
        assert "generation_image_dimensions_mismatch" not in codes, issues

        previous = Path.cwd()
        try:
            os.chdir(root)
            assert resolve_cli_path(plan_path, "visual/manifest.json") == manifest_path.resolve()
            assert resolve_cli_path(plan_path, "manifest.json") == manifest_path.resolve()
        finally:
            os.chdir(previous)

    print("native canvas and manifest path: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
