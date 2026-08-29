#!/usr/bin/env python3
"""Regression tests for the GordenImagePPTGen-compatible visual route."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_plan() -> dict:
    modules = []
    for index, name in enumerate(("海口抵达", "三亚海岸", "环岛体验", "返程收束"), start=1):
        modules.append({
            "label": f"模块 {index}",
            "title": name,
            "bullets": ["安排当天核心体验", "保留弹性与安全余量"],
            "kpi": f"D{index}",
            "tag": "建议",
            "source_refs": ["outline.md#slide-1"],
        })
    return {
        "schema": "ai-ppt-plus/visual-generation-plan/v1",
        "project_id": "visual-generation-fixture",
        "route": "visual-creation",
        "mode": "image-slide",
        "outline_revision": "outline-r1",
        "design_system_revision": "design-r1",
        "page_count": 1,
        "canvas": {"ratio": "16:9", "width_px": 2048, "height_px": 1152},
        "density_profile": "dense",
        "density_override_reason": "",
        "style_lock": {
            "name": "coastal-clear-tech",
            "palette": [
                {"name": "deep", "hex": "#14313B"},
                {"name": "sea", "hex": "#287B80"},
                {"name": "coral", "hex": "#E85B47"},
                {"name": "paper", "hex": "#F7F0E4"},
            ],
            "font_style": "clean sans-serif",
            "surface": "light paper with restrained depth",
            "icon_style": "flat line icons with consistent stroke",
            "avoid_items": ["placeholder text", "invented numbers", "random icon collage"],
        },
        "evidence_manifest": "visual-generation-manifest.json",
        "slides": [{
            "slide_no": 1,
            "page_type": "infographic",
            "title": "海南旅行攻略",
            "core_logic": "用一条由抵达、海岸、环岛到返程的路线组织一次轻松的海南旅行。",
            "visual_framework": "layered coastal journey map",
            "visual_generation_prompt": "Visual-only composition: a layered coastal journey map with a clear reading path and four anchored modules.",
            "production_prompt": "Create a polished 16:9 presentation slide in a layered coastal journey map. Use #14313B, #287B80, #E85B47 and #F7F0E4. Render the following 页面文字逐字: 海南旅行攻略; 把海岛节奏拆成四个易执行的旅行模块。; 模块 1; 海口抵达; D1; 建议; 安排当天核心体验; 保留弹性与安全余量; 模块 2; 三亚海岸; D2; 模块 3; 环岛体验; D3; 模块 4; 返程收束; D4; 先定节奏，再把风景留给临场发现。 Core logic: 用一条由抵达、海岸、环岛到返程的路线组织一次轻松的海南旅行。 不得编造任何数据; use clear hierarchy, restrained line icons and a readable route spine.",
            "content_model": {
                "intro": "把海岛节奏拆成四个易执行的旅行模块。",
                "modules": modules,
                "footer_banner": "先定节奏，再把风景留给临场发现。",
            },
            "formal_text": [{"id": "title", "role": "title", "text": "海南旅行攻略", "source_ref": "outline.md#slide-1"}],
            "visual_assets": {"icons": ["arrival", "coast", "route", "return"], "background_texture": "subtle wave contour"},
            "reference_images": [],
            "prompt_file": "prompts/slide-1.md",
        }],
    }


def main() -> int:
    try:
        from PIL import Image
    except ImportError:
        print("visual generation contract: skipped (Pillow unavailable)")
        return 0

    with tempfile.TemporaryDirectory(prefix="visual-generation-contract-") as temp:
        root = Path(temp)
        (root / "prompts").mkdir()
        prompt = root / "prompts" / "slide-1.md"
        source = root / "generated-source.png"
        copied = root / "project-copy.png"
        Image.new("RGB", (160, 90), (20, 60, 70)).save(source)
        copied.write_bytes(source.read_bytes())

        plan = root / "visual-generation-plan.json"
        plan_data = build_plan()
        prompt.write_text(plan_data["slides"][0]["production_prompt"] + "\n", encoding="utf-8")
        write_json(plan, plan_data)
        manifest = root / "visual-generation-manifest.json"
        write_json(manifest, {
            "schema": "ai-ppt-plus/visual-generation-manifest/v1",
            "project_id": "visual-generation-fixture",
            "plan_sha256": digest(plan),
            "slides": [{
                "slide_no": 1,
                "prompt_file": "prompts/slide-1.md",
                "generated_source": "generated-source.png",
                "copied_to": "project-copy.png",
                "generated_source_sha256": digest(source),
                "copied_to_sha256": digest(copied),
                "backend": "codex.imagegen",
                "model_or_tool": "image-generation",
                "canvas": {"ratio": "16:9"},
            }],
        })
        valid = run(
            "scripts/validate_visual_generation_plan.py", str(plan),
            "--manifest", str(manifest), "--expected-pages", "1", "--require-evidence",
        )
        assert valid.returncode == 0, valid.stdout + valid.stderr
        result = json.loads(valid.stdout)
        assert result["valid"] is True and result["evidence"]["record_count"] == 1, result

        route = root / "route.json"
        visual_manifest = root / "visual-intermediate-manifest.json"
        write_json(visual_manifest, {
            "image_path": "project-copy.png",
            "generator_skill": "GordenImagePPTGen",
            "model_or_tool": "image-generation",
            "prompt_or_recipe": "self-contained slide prompt",
            "review_status": "pending-human-review",
            "text_authority": "none",
        })
        write_json(route, {
            "schema": "ai-ppt-plus/route-decision/v1",
            "project_id": "visual-generation-fixture",
            "route": "visual-creation",
            "status": "decided",
            "visual_authority": "generated_visual_intermediate",
            "formal_content_authority": "approved_outline",
            "requires_image_generation": True,
            "visual_generation_mode": "image-slide",
            "visual_generation_plan": "visual-generation-plan.json",
            "visual_generation_manifest": "visual-generation-manifest.json",
            "reference_roster": [],
            "visual_intermediate_manifest": "visual-intermediate-manifest.json",
            "reason": "",
            "confirmed_by": "test",
            "confirmed_at": "2026-08-29T00:00:00Z",
        })
        route_result = run("scripts/validate_route.py", str(route), "--require-files", "--expected-pages", "1", "--require-confirmation")
        assert route_result.returncode == 0, route_result.stdout + route_result.stderr

        layout = root / "layout.json"
        write_json(layout, {
            "project_id": "visual-generation-fixture",
            "slide_width_in": 4,
            "slide_height_in": 2.25,
            "slides": [{"texts": [{"object_id": "title", "text": "Visual fixture", "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2, "size": 18}]}],
        })
        deck = root / "deck.pptx"
        composed = run("scripts/compose_pptx.py", str(layout), str(deck))
        assert composed.returncode == 0, composed.stdout + composed.stderr
        objects = root / "slide-object-manifest.json"
        built_objects = run("scripts/build_object_manifest.py", str(layout), "--output", str(objects))
        assert built_objects.returncode == 0, built_objects.stdout + built_objects.stderr
        slide_manifest = root / "slide-manifest.json"
        built_manifest = run("scripts/build_slide_manifest.py", str(layout), "--object-manifest", str(objects), "--output", str(slide_manifest))
        assert built_manifest.returncode == 0, built_manifest.stdout + built_manifest.stderr
        for name, value in (("handoff.json", {}), ("validation-report.json", {"status": "validated"}), ("issue-log.json", {"issues": []})):
            write_json(root / name, value)
        pipeline_run = root / "pipeline-run"
        pipeline = run(
            "scripts/run_pipeline.py", str(root), "--deck", str(deck), "--expected-pages", "1",
            "--route-decision", str(route), "--require-route", "--execution-mode", "linear",
            "--no-cache", "--output-dir", str(pipeline_run),
        )
        assert pipeline.returncode == 0, pipeline.stdout + pipeline.stderr
        pipeline_result = json.loads(pipeline.stdout.strip().splitlines()[-1])
        assert pipeline_result["quality_evidence"]["visual_generation_validation"]["valid"] is True, pipeline_result
        report_index = json.loads((pipeline_run / "report-index.json").read_text(encoding="utf-8"))
        visual_reports = [item for item in report_index["reports"] if item["report_type"] == "visual-generation-validation"]
        assert visual_reports and visual_reports[0]["step_ok"] is True, report_index

        invalid_plan = root / "invalid-plan.json"
        broken = build_plan()
        broken["evidence_manifest"] = None
        broken["slides"][0]["formal_text"] = []
        broken["slides"][0]["production_prompt"] = broken["slides"][0]["visual_generation_prompt"]
        write_json(invalid_plan, broken)
        invalid = run("scripts/validate_visual_generation_plan.py", str(invalid_plan), "--expected-pages", "1")
        assert invalid.returncode == 2, invalid.stdout + invalid.stderr
        assert "formal_text_missing_for_image_slide" in invalid.stdout
        assert "production_prompt_not_materialized" in invalid.stdout

    print("visual generation contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
