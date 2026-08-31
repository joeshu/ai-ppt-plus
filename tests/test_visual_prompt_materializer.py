#!/usr/bin/env python3
"""Regression tests for the visual-only A3 prompt materializer."""
from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_visual_generation_contract import attach_narrative_gate, build_plan  # noqa: E402


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/materialize_visual_generation_prompts.py", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def run_validator(plan: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/validate_visual_generation_plan.py", str(plan), "--expected-pages", "1"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="visual-prompt-materializer-") as temp:
        root = Path(temp)
        plan_data = build_plan()
        attach_narrative_gate(root, plan_data)
        plan_data.pop("evidence_manifest", None)
        slide = plan_data["slides"][0]
        slide.pop("production_prompt", None)
        slide.pop("prompt_file", None)
        plan = root / "visual-generation-plan.json"
        write_json(plan, plan_data)

        materialized = run(str(plan), "--in-place")
        assert materialized.returncode == 0, materialized.stdout + materialized.stderr
        result = json.loads(materialized.stdout)
        assert result["valid"] is True and result["production_prompts_materialized"] is True, result

        updated = json.loads(plan.read_text(encoding="utf-8"))
        updated_slide = updated["slides"][0]
        assert updated_slide["prompt_file"] == "prompts/01-slide.md"
        prompt_path = root / updated_slide["prompt_file"]
        prompt = prompt_path.read_text(encoding="utf-8")
        assert result["slides"][0]["prompt_sha256"] == digest(prompt_path)
        assert updated_slide["production_prompt"] in prompt
        for value in (
            "海南旅行攻略",
            "把海岛节奏拆成四个易执行的旅行模块。",
            "海口抵达",
            "安排当天核心体验",
            "D4",
            "先定节奏，再把风景留给临场发现。",
            "#14313B",
            "layered coastal journey map",
            "不得编造任何数据",
            "不得用代码补字或盖字",
        ):
            assert value in prompt, value
        assert "页面文字（逐字照排" in prompt
        assert "【参考图隔离规则】" in prompt
        assert "【区域蓝图（必须按区域分配容量）】" in prompt
        assert "主焦点：" in prompt
        assert "反模板护栏：" in prompt
        assert "【重点词着色语义（必须保留）】" in prompt
        assert "海南旅行攻略" in prompt and "范围：title" in prompt
        assert "【批准的图示标注】" in prompt
        assert "执行" in prompt and "inner loop" in prompt
        assert "【文字白名单（强约束）】" in prompt
        assert "只能出现上方【页面文字】" in prompt
        validated = run_validator(plan)
        assert validated.returncode == 0, validated.stdout + validated.stderr

        blocked = run(str(plan), "--in-place")
        assert blocked.returncode == 2
        blocked_result = json.loads(blocked.stdout)
        assert {item["code"] for item in blocked_result["issues"]} >= {"prompt_file_exists", "production_prompt_exists"}, blocked_result

        forced = run(str(plan), "--in-place", "--force")
        assert forced.returncode == 0, forced.stdout + forced.stderr

        dry_data = build_plan()
        dry_data.pop("evidence_manifest", None)
        dry_data["slides"][0].pop("production_prompt", None)
        dry_data["slides"][0].pop("prompt_file", None)
        dry_data["slides"][0]["prompt_file"] = "dry-prompts/01-slide.md"
        dry_plan = root / "dry-plan.json"
        write_json(dry_plan, dry_data)
        dry = run(str(dry_plan), "--dry-run")
        assert dry.returncode == 0, dry.stdout + dry.stderr
        assert not (root / "dry-prompts/01-slide.md").exists()
        dry_after = json.loads(dry_plan.read_text(encoding="utf-8"))
        assert "production_prompt" not in dry_after["slides"][0]

        invalid_data = build_plan()
        invalid_data.pop("evidence_manifest", None)
        invalid_data["slides"][0].pop("production_prompt", None)
        invalid_data["slides"][0].pop("prompt_file", None)
        invalid_data["slides"][0]["formal_text"][0]["text"] = "<待填写标题>"
        invalid_plan = root / "invalid-plan.json"
        write_json(invalid_plan, invalid_data)
        invalid = run(str(invalid_plan), "--dry-run")
        assert invalid.returncode == 2
        invalid_result = json.loads(invalid.stdout)
        assert any(item["code"] == "formal_text_placeholder" for item in invalid_result["issues"]), invalid_result

    print("visual prompt materializer: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
