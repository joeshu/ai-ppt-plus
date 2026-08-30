#!/usr/bin/env python3
"""Regression tests for single-source copy and one-encoding prompt rules."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from materialize_visual_generation_prompts import build_prompt, render_copy_values  # noqa: E402


def main() -> int:
    sentence = "建议调整至明天上午 9 点。"
    slide = {
        "slide_no": 1,
        "title": "唯一标题",
        "core_logic": "用一个主关系组织页面",
        "visual_framework": "asymmetric editorial information landscape",
        "visual_generation_prompt": "premium editorial composition",
        "closure_treatment": "inline close",
        "copy_contract": {
            "render_authority": "render_copy",
            "render_copy": ["唯一标题", sentence],
            "exact_once": True,
            "max_total_chars": 100,
        },
        "content_model": {
            "intro": sentence,
            "modules": [],
            "footer_banner": sentence,
        },
        "formal_text": [{"id": "conclusion", "role": "conclusion", "text": sentence, "source_ref": "approved#1"}],
    }
    plan = {
        "page_count": 1,
        "canvas": {"ratio": "16:9", "width_px": 2048, "height_px": 1152},
        "style_lock": {
            "palette": [{"name": "ink", "hex": "#14313B"}],
            "font_style": "clean sans",
            "surface": "paper",
            "icon_style": "line icons",
            "grid": "12 columns",
            "shared_chrome": "stable title zone",
            "material_language": "fine paper",
        },
        "generation_context": {"audience": "executives", "language": "zh-CN", "presentation_context": "meeting"},
        "retry_policy": {"max_attempts_per_slide": 2, "scope": "single-slide", "triggers": ["copy"]},
        "quality_target": {"readability": {"max_visible_copy_items": 10}},
        "generation_session": {"session_id": "test", "continuity_policy": "single-model-single-context", "batch_size": 1},
    }
    assert render_copy_values(slide) == ["唯一标题", sentence]
    prompt = build_prompt(plan, slide)
    assert prompt.count(f"「{sentence}」") == 1, prompt
    assert "只用于校对，不得再次排版" in prompt
    assert "每条最多出现一次" in prompt
    print("copy contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
