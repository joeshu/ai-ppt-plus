#!/usr/bin/env python3
"""Build the approved visual-generation plan for the 12 replay cases.

The case suite is the source of topics, formal copy and data requirements.  The
script only materializes the planning handoff; raster generation itself is
performed by the runtime image-generation tool and registered separately.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SUITE_PATH = ROOT / "case-suite.json"
OUTLINE_DIR = ROOT / "outline"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique(values):
    result = []
    for value in values:
        value = str(value).strip()
        if value and value not in result:
            result.append(value)
    return result


def data_tokens(value):
    tokens = []
    if isinstance(value, dict):
        for child in value.values():
            tokens.extend(data_tokens(child))
    elif isinstance(value, list):
        for child in value:
            tokens.extend(data_tokens(child))
    elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
        tokens.append(str(value))
    return tokens


def content_model(formal, data, case_index):
    source = unique(formal + data_tokens(data))
    while len(source) < 8:
        source.append(f"结构证据 {len(source) + 1:02d}")
    modules = []
    for index in range(4):
        offset = (index * 2) % len(source)
        modules.append({
            "label": source[offset],
            "title": source[(offset + 1) % len(source)],
            "bullets": [source[(offset + 2) % len(source)], source[(offset + 3) % len(source)]],
            "kpi": source[(offset + 4) % len(source)],
            "tag": source[(offset + 5) % len(source)],
            "source_refs": [f"case-suite.json#cases[{case_index}]"] ,
        })
    return {
        "intro": source[0],
        "modules": modules,
        "footer_banner": source[-1],
    }, source


def slide_plan(case, index):
    formal = unique([case["title"]] + [str(value) for value in case.get("formal_text", [])])
    model, copy = content_model(formal, case.get("data", {}), index)
    keyword = formal[-1] if formal else case["title"]
    return {
        "slide_no": index + 1,
        "outline_row_ref": f"outline/PPT思路表.csv#row:{index + 2}",
        "page_type": case["page_type"],
        "title": case["title"],
        "core_logic": f"围绕‘{case['title']}’建立一条可核对、可移动、可回放的页面关系。",
        "visual_framework": f"{case['page_type']}：以语义对象和证据链构成复杂信息框架",
        "visual_generation_prompt": case["prompt"],
        "closure_treatment": "将结论融入主框架或右侧结果舱；不强制使用全宽底栏。",
        "detailed_content_paragraphs": [
            f"页面以{case['title']}为唯一主题，使用批准案例中的正式文字和数据，建立清晰的管理层阅读入口。",
            f"页面主关系采用{case['page_type']}框架，区分面板、文字、表格、图表、连接线和独立视觉资产，避免重复编码同一关系。",
            "所有可核对的文字和数据保持可追溯；复杂渐变、图标和装饰只承担视觉语义，不承载正式文字。",
        ],
        "layout_blueprint": {
            "focal_point": f"{case['title']}的主关系与结果区域",
            "reading_path": "标题与结论 → 主框架 → 证据面板/表格 → 结果或门禁",
            "zones": [
                {"name": "header", "purpose": "标题、结论和页级识别", "position": "top", "content_capacity": "一个标题与一个短结论"},
                {"name": "primary-framework", "purpose": "承载页面主关系", "position": "center", "content_capacity": "主要节点、连接线、面板或图表"},
                {"name": "evidence-rail", "purpose": "承载可核对数据和辅助说明", "position": "right-or-bottom", "content_capacity": "两到三组证据"},
                {"name": "closure", "purpose": "结果、风险或下一步", "position": "page-local", "content_capacity": "一个短收束，不固定成横幅"},
            ],
            "anti_template_rules": [
                "不得把页面做成无语义的等尺寸卡片墙",
                "不得用第二套编号重复同一条关系",
                "表格、面板和正文必须保留明确视觉边界",
            ],
        },
        "keyword_emphasis": {
            "rules": ["只对批准文字中的关键词做行内强调，不新增或改写正式文字。"],
            "items": [{"text": keyword, "color": "#E60012", "scope": "page conclusion or action close", "treatment": "inline emphasis"}],
        },
        "visual_assertions": {
            "ocr_lang": "chi_sim+eng",
            "ocr_failure_policy": "manual-review",
            "readback_scope": "all-render-copy",
            "must_contain_text": [case["title"]],
            "forbidden_text": ["placeholder", "Lorem", "待补充", "示意文字"],
            "min_ink_ratio": 0.01,
        },
        "diagram_annotations": [
            {"text": formal[1] if len(formal) > 1 else case["title"], "purpose": "标记主关系中的一个批准节点", "scope": "primary framework", "approved_by": "user-directed case suite", "source_ref": f"case-suite.json#cases[{index}].formal_text"},
        ],
        "reference_treatment": {
            "mode": "none",
            "source_role": "无外部参考图；以本案例生成图作为后续还原的固定视觉权威",
            "preserve": ["本套案例的16:9画布和统一设计锁"],
            "exclude": ["未批准文字、虚构数据、未授权品牌标记"],
        },
        "copy_contract": {
            "render_authority": "render_copy",
            "render_copy": copy,
            "exact_once": True,
            "max_total_chars": 900,
        },
        "representation_policy": {
            "one_primary_encoding": True,
            "avoid_duplicate_summary": True,
            "secondary_elements": "只增加新的决策线索或证据，不重复主关系、结论或步骤。",
            "prohibited_patterns": ["同一关系使用两套编号", "重复结论栏", "表格与图片重复承载同一数据"],
        },
        "content_model": model,
        "formal_text": [
            {"id": f"case-{index + 1:02d}-text-{text_index + 1:02d}", "role": "title" if text_index == 0 else "copy", "text": value, "source_ref": f"case-suite.json#cases[{index}].formal_text[{text_index}]"}
            for text_index, value in enumerate(formal)
        ],
        "visual_assets": {"icons": case.get("native_requirements", []), "background_texture": "深海蓝网格、细线和克制光晕"},
        "reference_images": [],
        "prompt_file": f"prompts/{index + 1:02d}-{case['case_id']}.md",
    }


def main():
    suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    cases = suite["cases"]
    OUTLINE_DIR.mkdir(parents=True, exist_ok=True)
    outline_path = OUTLINE_DIR / "PPT思路表.csv"
    with outline_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["slide_no", "title_core_idea", "page_outline", "owner_notes", "status", "data_sources", "visual_type"])
        writer.writeheader()
        for index, case in enumerate(cases, start=1):
            writer.writerow({
                "slide_no": index,
                "title_core_idea": f"{case['title']}｜{case['page_type']}关系可回放、可编辑、可核对",
                "page_outline": f"{case['title']}；覆盖{case['page_type']}主框架、正式文字、可核对数据和对应的原生对象要求。",
                "owner_notes": "用户已授权本轮为蒸馏回放案例集设定主题并生成单页视觉稿。",
                "status": "approved",
                "data_sources": f"case-suite.json#cases[{index - 1}]",
                "visual_type": case["page_type"],
            })
    change_log = {
        "schema": "ai-ppt-plus/outline-change-log/v1",
        "revision": "R1-case-replay-12",
        "source": "user-directed case replay suite",
        "changes": [{"slide_no": index, "change": "建立单页高密度视觉回放案例，正式文字和数据绑定 case-suite.json。"} for index, _ in enumerate(cases, start=1)],
    }
    (OUTLINE_DIR / "PPT思路表-change-log.json").write_text(json.dumps(change_log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plan = {
        "schema": "ai-ppt-plus/visual-generation-plan/v1",
        "project_id": "distillation-case-replay-12",
        "route": "visual-creation",
        "mode": "image-slide",
        "outline_revision": "R1-case-replay-12",
        "design_system_revision": "R1-luxury-dense-navy-red",
        "narrative_gate": {
            "schema": "ai-ppt-plus/narrative-gate/v1",
            "workflow": "ppt-thought-table-first",
            "outline_table": "outline/PPT思路表.csv",
            "outline_table_sha256": digest(outline_path),
            "revision": "R1-case-replay-12",
            "status": "approved",
            "approval_required": True,
            "approved_by": "user-directed case suite",
            "approved_at": "2026-09-02T00:00:00Z",
            "feedback_round": 0,
            "owner_notes_preserved": True,
            "formal_text_authority": "approved-outline-table",
            "change_log": "outline/PPT思路表-change-log.json",
        },
        "page_count": len(cases),
        "canvas": {"ratio": "16:9", "width_px": 2048, "height_px": 1152},
        "canvas_policy": {"require_exact_dimensions": False, "minimum_width_px": 1600, "minimum_height_px": 900, "on_mismatch": "warn"},
        "density_profile": "dense",
        "density_override_reason": "",
        "generation_context": {"audience": "国企经营管理层、业务负责人和专业评审", "language": "简体中文，必要时保留短英文标签", "presentation_context": "高端管理层会议室单页评审"},
        "retry_policy": {"max_attempts_per_slide": 2, "scope": "single-slide", "triggers": ["image-generation failure", "missing or garbled approved copy", "collapsed reading path or unusable layout"]},
        "style_lock": {
            "name": "case-replay-luxury-dense-v1",
            "palette": [{"name": "primary", "hex": "#061A35"}, {"name": "accent-red", "hex": "#E60012"}, {"name": "electric-blue", "hex": "#1687FF"}, {"name": "silver", "hex": "#F4F7FB"}],
            "font_style": "Noto Sans CJK SC / clean executive sans-serif",
            "surface": "deep-sea navy glass, restrained metallic red and electric blue",
            "icon_style": "consistent fine-line enterprise icons",
            "grid": "12-column 16:9 executive grid with stable title baseline and safe margins",
            "shared_chrome": "same title baseline, color system, evidence discipline and independent semantic regions; closure remains page-local",
            "material_language": "luxurious through precise hierarchy, glass depth, fine linework, controlled glow and no decorative noise",
            "avoid_items": ["placeholder text", "invented numbers", "watermark", "random icon collage", "full-slide screenshot skin"],
        },
        "quality_target": {
            "tier": "premium-commercial",
            "visual_language": "luxury high-density executive information design with complex but legible semantic structure",
            "must_have": ["one unambiguous focal point per page", "complex but readable layout", "presentation-scale typography", "precise alignment and layered material depth", "semantic regions suitable for later native reconstruction"],
            "avoid_items": ["generic four-card template", "neon HUD", "fake charts", "unapproved English labels", "watermarks"],
            "readability": {"target_viewing": "16:9 meeting-room presentation", "min_title_px": 56, "min_body_px": 28, "min_annotation_px": 22, "max_visible_copy_items": 30},
            "commercial_policy": {"exclude_unlicensed_logos": True, "exclude_watermarks": True, "exclude_celebrity_and_trademark_imitation": True, "external_asset_provenance_required": True},
        },
        "generation_session": {"session_id": "case-replay-12-imagegen-session-R1", "continuity_policy": "single-model-single-context", "batch_size": 6, "style_anchor": "design-system:case-replay-luxury-dense-v1", "shared_preamble": "同一套案例使用同一模型、同一上下文和同一设计锁；只改变页面叙事框架，不改变材质、字级和视觉语言。"},
        "generation_contract": {"skill": "ai-ppt-visual-gen", "tool_resolution": "runtime-discovery", "preferred_tool": "imagegen", "backend_policy": "raster-only", "source_retention": "generated-source-and-project-copy", "no_code_overlay": True},
        "evidence_manifest": "visual-generation-manifest.json",
        "slides": [slide_plan(case, index) for index, case in enumerate(cases)],
    }
    (ROOT / "visual-generation-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"plan": str(ROOT / "visual-generation-plan.json"), "outline": str(outline_path), "pages": len(cases)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
