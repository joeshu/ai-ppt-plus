#!/usr/bin/env python3
"""Exercise the self-contained Super skill's deterministic A-to-B handoff."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_visual_generation_contract import build_plan  # noqa: E402


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    try:
        from PIL import Image
    except ImportError:
        print("super pipeline: skipped (Pillow unavailable)")
        return 0
    with tempfile.TemporaryDirectory(prefix="super-pipeline-") as temp:
        project = Path(temp)
        prompt = project / "prompts" / "slide-1.md"
        prompt.parent.mkdir()
        source = project / "generated-source.png"
        copied = project / "slide-1.png"
        Image.new("RGB", (160, 90), (24, 64, 82)).save(source)
        copied.write_bytes(source.read_bytes())
        plan = project / "visual-generation-plan.json"
        plan_data = build_plan()
        plan_data["slides"][0]["prompt_file"] = "prompts/slide-1.md"
        prompt.write_text(plan_data["slides"][0]["production_prompt"] + "\n", encoding="utf-8")
        write_json(plan, plan_data)
        manifest = project / "visual-generation-manifest.json"
        write_json(manifest, {
            "schema": "ai-ppt-plus/visual-generation-manifest/v1",
            "project_id": plan_data["project_id"],
            "plan_sha256": digest(plan),
            "generator_skill": "ai-ppt-visual-gen",
            "tool_resolution": "runtime-discovery",
            "backend_policy": "raster-only",
            "source_retention": "generated-source-and-project-copy",
            "no_code_overlay": True,
            "slides": [{
                "slide_no": 1,
                "prompt_file": "prompts/slide-1.md",
                "prompt_sha256": digest(prompt),
                "generated_source": source.name,
                "copied_to": copied.name,
                "generated_source_sha256": digest(source),
                "copied_to_sha256": digest(copied),
                "backend": "test-imagegen",
                "model_or_tool": "fixture",
                "canvas": {"width_px": 160, "height_px": 90, "ratio": "16:9"},
            }],
        })
        layout = project / "editable-layout.json"
        write_json(layout, {
            "project_id": "super-pipeline",
            "slide_width_in": 13.333333,
            "slide_height_in": 7.5,
            "slides": [{
                "background_color": "F7F8FA",
                "texts": [{"object_id": "title", "text": "A→B 串联完成", "x": 0.08, "y": 0.08, "w": 0.45, "h": 0.12, "size": 28}],
            }],
        })
        deck = project / "editable.pptx"
        completed = subprocess.run([
            sys.executable,
            "scripts/run_super_pipeline.py",
            str(project),
            "--visual-plan", str(plan),
            "--visual-manifest", str(manifest),
            "--editable-layout", str(layout),
            "--output-deck", str(deck),
            "--expected-pages", "1",
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        result = json.loads(completed.stdout)
        assert result["valid"] is True
        assert [item["name"] for item in result["steps"]] == [
            "bundle", "A-visual", "B-editable-compose", "B-editable-inspect"
        ]
        assert deck.is_file()
        assert (project / "qa" / "visual-deck-strip.png").is_file()
        assert (project / "qa" / "editable-inspection.json").is_file()
    print("super A-to-B pipeline: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
