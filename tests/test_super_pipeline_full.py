#!/usr/bin/env python3
"""Exercise the full Super A→B pipeline and its v2 handoff contract."""
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


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    try:
        from PIL import Image
    except ImportError:
        print("super full pipeline: skipped (Pillow unavailable)")
        return 0

    with tempfile.TemporaryDirectory(prefix="super-full-pipeline-") as temp:
        project = Path(temp)
        source = project / "generated-source.png"
        copied = project / "slide-1.png"
        Image.new("RGB", (160, 90), (24, 64, 82)).save(source)
        copied.write_bytes(source.read_bytes())

        plan = project / "visual-generation-plan.json"
        plan_data = build_plan()
        plan_data["project_id"] = "super-full-fixture"
        plan_data["slides"][0]["prompt_file"] = "prompts/slide-1.md"
        prompt = project / "prompts" / "slide-1.md"
        prompt.parent.mkdir()
        prompt.write_text(plan_data["slides"][0]["production_prompt"] + "\n", encoding="utf-8")
        write_json(plan, plan_data)

        generation_manifest = project / "visual-generation-manifest.json"
        write_json(generation_manifest, {
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

        visual_intermediate = project / "visual-intermediate-manifest.json"
        write_json(visual_intermediate, {
            "image_path": copied.name,
            "generator_skill": "ai-ppt-visual-gen",
            "model_or_tool": "fixture",
            "prompt_or_recipe": "self-contained slide prompt",
            "review_status": "pending-human-review",
            "text_authority": "none",
        })
        route = project / "route.json"
        write_json(route, {
            "schema": "ai-ppt-plus/route-decision/v1",
            "project_id": plan_data["project_id"],
            "route": "visual-creation",
            "status": "decided",
            "visual_authority": "generated_visual_intermediate",
            "formal_content_authority": "approved_outline",
            "requires_image_generation": True,
            "visual_generation_mode": "image-slide",
            "visual_generation_plan": plan.name,
            "visual_generation_manifest": generation_manifest.name,
            "reference_roster": [],
            "visual_intermediate_manifest": visual_intermediate.name,
            "reason": "",
            "confirmed_by": "test",
            "confirmed_at": "2026-08-29T00:00:00Z",
        })

        layout = project / "layout.json"
        write_json(layout, {
            "project_id": plan_data["project_id"],
            "slide_width_in": 13.333333,
            "slide_height_in": 7.5,
            "slides": [{
                "background": copied.name,
                "background_color": "F7F8FA",
                "texts": [{
                    "object_id": "title",
                    "text": "A→B 串联完成",
                    "x": 0.08,
                    "y": 0.08,
                    "w": 0.45,
                    "h": 0.12,
                    "size": 28,
                }],
            }],
        })

        objects = project / "slide-object-manifest.json"
        built_objects = run("ai-ppt-editable/scripts/build_object_manifest.py", str(layout), "--output", str(objects))
        assert built_objects.returncode == 0, built_objects.stdout + built_objects.stderr
        slide_manifest = project / "slide-manifest.json"
        built_manifest = run(
            "ai-ppt-editable/scripts/build_slide_manifest.py", str(layout),
            "--object-manifest", str(objects), "--output", str(slide_manifest),
        )
        assert built_manifest.returncode == 0, built_manifest.stdout + built_manifest.stderr
        write_json(project / "validation-report.json", {"status": "reconstruction", "issues": []})
        write_json(project / "issue-log.json", {"issues": []})

        deck = project / "editable.pptx"
        completed = run(
            "scripts/run_super_pipeline.py", str(project), "--mode", "full",
            "--visual-plan", str(plan), "--visual-manifest", str(generation_manifest),
            "--editable-layout", str(layout), "--output-deck", str(deck),
            "--expected-pages", "1", "--route-decision", str(route),
            "--execution-mode", "linear", "--no-cache",
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        assert result["valid"] is True, result
        assert [item["name"] for item in result["steps"]] == [
            "bundle", "environment", "environment-contract", "route", "A-visual", "B-editable-compose",
            "B-editable-inspect", "handoff-build", "B-editable-qa",
            "handoff-finalize", "handoff-validate",
        ], result["steps"]
        handoff = project / "handoff.json"
        handoff_data = json.loads(handoff.read_text(encoding="utf-8"))
        assert handoff_data["schema"] == "ai-ppt-plus/handoff/v2", handoff_data
        assert handoff_data["current_stage"] == "validated", handoff_data
        assert handoff_data["remaining_slides"] == [], handoff_data
        assert deck.is_file()
        assert (project / "qa" / "visual-deck-strip.png").is_file()
        assert (project / "super-pipeline-runs" / result["run_id"] / "handoff-validate.stdout.txt").is_file()

    print("super full A-to-B pipeline: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
