#!/usr/bin/env python3
"""Materialize self-contained A3 prompts from a visual-generation plan.

This helper owns only the ``visual-creation`` / ``image-slide`` planning
stage.  It writes prompt text and, when requested, adds the derived
``production_prompt`` values to the plan.  It never calls an image model,
draws a bitmap, composes a PPTX, or enters the image-to-editable-PPTX route.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from atomic_output import atomic_write_json, atomic_write_text  # noqa: E402
from validate_visual_generation_plan import (  # noqa: E402
    GENERATION_CONTRACT,
    HEX_RE,
    PLACEHOLDER_RE,
    PLAN_SCHEMA,
    formal_text_entries,
    text_value,
)


MATERIALIZATION_SCHEMA = "ai-ppt-plus/visual-prompt-materialization/v1"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def visible_scalar(value) -> str:
    """Read a copy-bearing scalar, including the common ``{"text": ...}`` form."""
    if isinstance(value, dict):
        return text_value(value.get("text", value.get("value")))
    return text_value(value)


def module_bullets(module: dict) -> list[str]:
    bullets = module.get("bullets", module.get("points", []))
    if isinstance(bullets, (str, int, float)) and not isinstance(bullets, bool):
        bullets = [bullets]
    if not isinstance(bullets, list):
        return []
    return [value for value in (visible_scalar(item) for item in bullets) if value]


def content_model(slide: dict) -> dict:
    value = slide.get("content_model")
    return value if isinstance(value, dict) else {}


def content_entries(slide: dict) -> list[dict]:
    """Return visible content in the same order used by the page model."""
    content = content_model(slide)
    entries: list[dict] = []
    intro = visible_scalar(content.get("intro"))
    if intro:
        entries.append({"role": "intro", "text": intro})
    modules = content.get("modules") or []
    if isinstance(modules, list):
        for index, module in enumerate(modules, start=1):
            if not isinstance(module, dict):
                continue
            for role, field in (("label", "label"), ("title", "title"), ("kpi", "kpi"), ("tag", "tag")):
                value = visible_scalar(module.get(field))
                if value:
                    entries.append({"role": f"module-{index}-{role}", "text": value})
            for bullet_index, bullet in enumerate(module_bullets(module), start=1):
                entries.append({"role": f"module-{index}-bullet-{bullet_index}", "text": bullet})
    footer = visible_scalar(content.get("footer_banner"))
    if footer:
        entries.append({"role": "footer", "text": footer})
    return entries


def all_visible_text(slide: dict) -> list[str]:
    """Collect every page string without duplicating exact copies."""
    values: list[str] = []
    for value in (slide.get("title"), slide.get("sub_title")):
        text = visible_scalar(value)
        if text:
            values.append(text)
    for entry in formal_text_entries(slide):
        if entry["text"]:
            values.append(entry["text"])
    values.extend(entry["text"] for entry in content_entries(slide))
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def palette_entries(plan: dict) -> list[tuple[str, str]]:
    style = plan.get("style_lock") if isinstance(plan.get("style_lock"), dict) else {}
    palette = style.get("palette") if isinstance(style.get("palette"), list) else []
    result: list[tuple[str, str]] = []
    for index, item in enumerate(palette, start=1):
        if isinstance(item, dict):
            name = visible_scalar(item.get("name")) or f"color-{index}"
            color = visible_scalar(item.get("hex"))
        else:
            name = f"color-{index}"
            color = visible_scalar(item)
        if color:
            result.append((name, color))
    return result


def format_visual_assets(slide: dict) -> str:
    assets = slide.get("visual_assets") if isinstance(slide.get("visual_assets"), dict) else {}
    icons = assets.get("icons") if isinstance(assets.get("icons"), list) else []
    icons = [visible_scalar(item) for item in icons if visible_scalar(item)]
    background = visible_scalar(assets.get("background_texture")) or "无额外背景纹理"
    icon_text = "、".join(icons) if icons else "按页面语义使用少量统一线性图标"
    return f"图标语义：{icon_text}\n背景纹理：{background}"


def reference_policy(slide: dict) -> str:
    references = slide.get("reference_images") or []
    if not isinstance(references, list) or not references:
        return "无外部参考图；不得引入未经批准的文字、配色或品牌元素。"
    paths = []
    for item in references:
        if isinstance(item, dict):
            value = visible_scalar(item.get("path", item.get("file", item.get("id"))))
        else:
            value = visible_scalar(item)
        if value:
            paths.append(value)
    listed = "、".join(paths) if paths else "已声明的参考图"
    return (
        f"参考图：{listed}。只参考排版/构图，不使用其文字，不使用其配色，"
        "不使用其品牌元素；不得复制其 logo、专名、数据或装饰性文案。"
    )


def quote_copy(value: str) -> str:
    """Keep the copy verbatim while making section boundaries readable."""
    return f"「{value}」"


def build_prompt(plan: dict, slide: dict) -> str:
    canvas = plan.get("canvas") if isinstance(plan.get("canvas"), dict) else {}
    ratio = visible_scalar(canvas.get("ratio")) or "16:9"
    width = visible_scalar(canvas.get("width_px"))
    height = visible_scalar(canvas.get("height_px"))
    dimensions = f"，目标约 {width}×{height} 像素" if width and height else ""
    style = plan.get("style_lock") if isinstance(plan.get("style_lock"), dict) else {}
    palette = palette_entries(plan)
    palette_text = "；".join(f"{name} {color}" for name, color in palette)
    font_style = visible_scalar(style.get("font_style")) or "干净的无衬线字体"
    surface = visible_scalar(style.get("surface")) or "克制、有层次的演示页表面"
    icon_style = visible_scalar(style.get("icon_style")) or "统一笔画的语义图标"
    avoid_items = style.get("avoid_items") if isinstance(style.get("avoid_items"), list) else []
    avoid_text = "、".join(visible_scalar(item) for item in avoid_items if visible_scalar(item))
    if not avoid_text:
        avoid_text = "占位文字、虚构数据、大面积纯绿色、随机图标拼贴"

    page_type = visible_scalar(slide.get("page_type")) or "infographic"
    title = visible_scalar(slide.get("title"))
    core_logic = visible_scalar(slide.get("core_logic"))
    framework = visible_scalar(slide.get("visual_framework"))
    visual_prompt = visible_scalar(slide.get("visual_generation_prompt"))
    content = content_model(slide)
    modules = content.get("modules") if isinstance(content.get("modules"), list) else []

    module_lines: list[str] = []
    intro = visible_scalar(content.get("intro"))
    if intro:
        module_lines.append(f"导语：{quote_copy(intro)}")
    for index, module in enumerate(modules, start=1):
        if not isinstance(module, dict):
            continue
        module_lines.append(f"模块 {index}：")
        for label, field in (("子标签", "label"), ("标题", "title"), ("重点数字", "kpi"), ("标签药丸", "tag")):
            value = visible_scalar(module.get(field))
            if value:
                module_lines.append(f"  {label}：{quote_copy(value)}")
        for bullet in module_bullets(module):
            module_lines.append(f"  要点：{quote_copy(bullet)}")
    footer = visible_scalar(content.get("footer_banner"))
    if footer:
        module_lines.append(f"底部总结横幅：{quote_copy(footer)}")
    content_block = "\n".join(module_lines) if module_lines else "按正式文字组织清晰的页面层级。"

    formal_lines = []
    for entry in formal_text_entries(slide):
        formal_lines.append(f"- [{entry['role']}] {quote_copy(entry['text'])}")
    formal_block = "\n".join(formal_lines) if formal_lines else "- 无"

    visible_lines = "\n".join(f"- {quote_copy(value)}" for value in all_visible_text(slide))
    if not visible_lines:
        visible_lines = "- 无"

    return f"""生成一张 {ratio} 横版图片型演示幻灯片{dimensions}。画面要适合会议室观看，四周保留安全边距，关键文字不要贴边；必须使用真实 raster 图像生成后端。

【整体风格】
统一遵循本 deck 的设计系统：{surface}；字体为{font_style}；图标为{icon_style}；配色固定为：{palette_text}。信息密度与层级要清晰，重点数字最大，标题次之，正文可读，模块严格对齐。

【本页角色与叙事】
页面类型：{page_type}
本页标题：{quote_copy(title)}
核心逻辑：{quote_copy(core_logic)}
视觉框架：{framework}。使用该框架组织阅读路径，但不要把“视觉框架”这个元标签额外渲染到画面上。

【版式结构】
沿着“页眉标题区 → 主体视觉框架 → 模块/图表说明 → 底部结论横幅”的阅读路径构图；顶部建立标题、导语和短强调线，中部用 {framework} 承载模块，保留清晰的焦点、留白、连接线和语义化微件。每个模块至少具备标题、要点、重点数字或标签层级；不要退化成无信息的通用卡片模板。

【视觉生成描述】
{visual_prompt}
以上段落只描述画面、材质、光照和视觉流向；它不是完整出图指令，必须与下面的正式文字合并执行。

【页面内容结构】
{content_block}

【页面文字（逐字照排，必须全部出现）】
以下所有文字必须原样保留，包含中文标点、数字、大小写和专名；不得改写、删减、翻译、补充事实，也不得生成额外的事实性标签：
{visible_lines}

【正式文字来源锚点】
以下是 approved outline / formal copy 的逐字文本，优先级高于任何视觉参考；全部必须出现：
{formal_block}

【图标与装饰】
{format_visual_assets(slide)}
使用克制的线性/扁平商务图标、连接线、箭头、标签药丸、进度或节点微件提升信息密度；装饰不得抢夺核心文字焦点。

【字体与可读性】
重点数字 > 主标题 > 模块标题 > 子标签 > 正文要点。标题约为正文 2.5–3 倍，重点数字再放大；正文不要小到会议室不可读，单卡正文控制在 2–4 行，保持高对比与统一字重。

【参考图隔离规则】
{reference_policy(slide)}

【生成硬约束】
不得编造任何数据、日期、机构、地名或专名；不得使用 SVG、HTML、Canvas、Pillow、ImageMagick 或其它代码绘图冒充 raster 出图；不得用代码补字或盖字，文字错漏只能修改本提示词后重新生成。不得加入页码、logo、水印或未批准的品牌元素。避免：{avoid_text}。成品必须是包含全部上述真实文字的完整图片型幻灯片，不是占位模板、空卡片或无字背景。"""


def inside(root: Path, path: Path) -> bool:
    return path == root or root in path.parents


def prompt_target(plan_path: Path, slide: dict) -> tuple[str, Path]:
    slide_no = slide.get("slide_no")
    value = visible_scalar(slide.get("prompt_file"))
    relative = value or f"prompts/{int(slide_no):02d}-slide.md"
    path_value = Path(relative)
    if ".." in path_value.parts:
        raise ValueError("prompt_file_parent_traversal")
    path = path_value.resolve() if path_value.is_absolute() else (plan_path.parent / path_value).resolve()
    if not inside(plan_path.parent, path):
        raise ValueError("prompt_file_outside_plan_root")
    return relative, path


def validate_input(plan: object) -> list[dict]:
    issues: list[dict] = []

    def issue(code: str, **details) -> None:
        item = {"severity": "blocker", "code": code}
        item.update(details)
        issues.append(item)

    if not isinstance(plan, dict):
        issue("plan_not_object")
        return issues
    if not visible_scalar(plan.get("project_id")):
        issue("plan_project_id_missing")
    for field in ("outline_revision", "design_system_revision"):
        if not visible_scalar(plan.get(field)):
            issue("plan_revision_missing", field=field)
    if plan.get("schema") != PLAN_SCHEMA:
        issue("plan_schema_invalid", observed=plan.get("schema"))
    if plan.get("route") != "visual-creation":
        issue("plan_route_invalid", observed=plan.get("route"))
    if plan.get("mode") != "image-slide":
        issue("plan_mode_not_materializable", observed=plan.get("mode"))
    contract = plan.get("generation_contract")
    if not isinstance(contract, dict):
        issue("generation_contract_missing")
        contract = {}
    for field, expected in GENERATION_CONTRACT.items():
        if contract.get(field) != expected:
            issue("generation_contract_mismatch", field=field, expected=expected, observed=contract.get(field))
    if contract.get("no_code_overlay") is not True:
        issue("generation_contract_no_code_overlay_missing")
    canvas = plan.get("canvas") if isinstance(plan.get("canvas"), dict) else {}
    ratio = visible_scalar(canvas.get("ratio"))
    if ratio not in {"16:9", "3:2"}:
        issue("canvas_ratio_invalid", observed=ratio)
    style = plan.get("style_lock") if isinstance(plan.get("style_lock"), dict) else {}
    palette = style.get("palette") if isinstance(style.get("palette"), list) else []
    if len(palette) < 3:
        issue("style_lock_palette_too_small")
    for index, item in enumerate(palette):
        color = visible_scalar(item.get("hex")) if isinstance(item, dict) else visible_scalar(item)
        if not HEX_RE.fullmatch(color):
            issue("style_lock_palette_color_invalid", index=index, observed=color)
    for field in ("font_style", "surface", "icon_style"):
        if not visible_scalar(style.get(field)):
            issue("style_lock_field_missing", field=field)
    slides = plan.get("slides")
    if not isinstance(slides, list) or not slides:
        issue("plan_slides_missing")
        return issues
    try:
        page_count = int(plan.get("page_count"))
    except (TypeError, ValueError):
        page_count = 0
    if page_count < 1:
        issue("plan_page_count_invalid", observed=plan.get("page_count"))
    elif page_count != len(slides):
        issue("plan_slide_count_mismatch", expected=page_count, observed=len(slides))
    numbers: set[int] = set()
    for index, slide in enumerate(slides):
        if not isinstance(slide, dict):
            issue("plan_slide_invalid", index=index)
            continue
        slide_no = slide.get("slide_no")
        if not isinstance(slide_no, int) or slide_no < 1:
            issue("plan_slide_number_invalid", index=index)
            slide_no = index + 1
        elif slide_no in numbers:
            issue("plan_slide_number_duplicate", slide_no=slide_no)
        numbers.add(slide_no)
        for field in ("page_type", "title", "core_logic", "visual_framework", "visual_generation_prompt"):
            if not visible_scalar(slide.get(field)):
                issue("plan_slide_field_missing", slide_no=slide_no, field=field)
        content = content_model(slide)
        if not isinstance(slide.get("content_model"), dict):
            issue("content_model_missing", slide_no=slide_no)
        modules = content.get("modules") if isinstance(content.get("modules"), list) else []
        for module_index, module in enumerate(modules, start=1):
            if not isinstance(module, dict):
                issue("content_module_invalid", slide_no=slide_no, module=module_index)
                continue
            refs = module.get("source_refs")
            if not isinstance(refs, list) or not any(visible_scalar(item) for item in refs):
                issue("content_module_source_reference_missing", slide_no=slide_no, module=module_index)
        entries = formal_text_entries(slide)
        if not entries:
            issue("formal_text_missing", slide_no=slide_no)
        for entry in entries:
            if not entry["text"]:
                issue("formal_text_empty", slide_no=slide_no, text_id=entry["id"])
            elif PLACEHOLDER_RE.search(entry["text"]):
                issue("formal_text_placeholder", slide_no=slide_no, text_id=entry["id"])
            if not visible_scalar(entry.get("source_ref")):
                issue("formal_text_source_reference_missing", slide_no=slide_no, text_id=entry["id"])
        for value in all_visible_text(slide):
            if PLACEHOLDER_RE.search(value):
                issue("content_text_placeholder", slide_no=slide_no, text=value)
    return issues


def result_for(plan_path: Path, valid: bool, issues: list[dict], **details) -> dict:
    result = {
        "schema": MATERIALIZATION_SCHEMA,
        "valid": valid,
        "technical_valid": valid,
        "status": "passed" if valid else "blocked",
        "plan_path": str(plan_path),
        "issues": issues,
    }
    result.update(details)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", help="visual-generation-plan.json")
    parser.add_argument("--in-place", action="store_true", help="write prompts and update production_prompt fields in the plan")
    parser.add_argument("--force", action="store_true", help="allow replacing existing prompt files and derived production prompts")
    parser.add_argument("--dry-run", action="store_true", help="validate and preview materialization without writing files")
    parser.add_argument("--report", help="write a JSON materialization report")
    args = parser.parse_args()

    plan_path = Path(args.plan).resolve()
    issues: list[dict] = []
    try:
        plan = read_json(plan_path)
    except Exception as exc:
        result = result_for(plan_path, False, [{"severity": "blocker", "code": "plan_invalid_json", "message": f"{type(exc).__name__}: {exc}"}])
        if args.report:
            atomic_write_json(Path(args.report).resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 2

    issues.extend(validate_input(plan))
    if not args.in_place and not args.dry_run:
        issues.append({"severity": "blocker", "code": "in_place_or_dry_run_required"})
    if issues:
        result = result_for(plan_path, False, issues, slides=[])
        if args.report:
            atomic_write_json(Path(args.report).resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 2

    updated_plan = copy.deepcopy(plan)
    generated: list[dict] = []
    seen_targets: set[Path] = set()
    for slide_index, slide in enumerate(plan.get("slides", [])):
        slide_no = slide.get("slide_no", slide_index + 1)
        try:
            relative_prompt, target = prompt_target(plan_path, slide)
        except (TypeError, ValueError) as exc:
            issues.append({"severity": "blocker", "code": str(exc), "slide_no": slide_no})
            continue
        if target in seen_targets:
            issues.append({"severity": "blocker", "code": "prompt_file_duplicate", "slide_no": slide_no, "path": str(target)})
            continue
        seen_targets.add(target)
        if args.in_place and not args.force:
            if target.is_file():
                issues.append({"severity": "blocker", "code": "prompt_file_exists", "slide_no": slide_no, "path": str(target)})
            if visible_scalar(slide.get("production_prompt")):
                issues.append({"severity": "blocker", "code": "production_prompt_exists", "slide_no": slide_no})
        prompt = build_prompt(plan, slide)
        updated_plan["slides"][slide_index]["prompt_file"] = relative_prompt
        updated_plan["slides"][slide_index]["production_prompt"] = prompt
        generated.append({
            "slide_no": slide_no,
            "prompt_file": relative_prompt,
            "path": str(target),
            "characters": len(prompt),
            "text_items": len(all_visible_text(slide)),
        })

    if issues:
        result = result_for(plan_path, False, issues, slides=generated, in_place=args.in_place, force=args.force)
        if args.report:
            atomic_write_json(Path(args.report).resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 2

    if not args.dry_run:
        try:
            for index, item in enumerate(generated):
                prompt = build_prompt(plan, plan["slides"][index])
                atomic_write_text(Path(item["path"]), prompt + "\n", suffix=f".tmp.prompt-{item['slide_no']}")
            atomic_write_json(plan_path, updated_plan)
        except Exception as exc:
            issues.append({"severity": "blocker", "code": "materialization_write_failed", "message": f"{type(exc).__name__}: {exc}"})

    valid = not issues
    result = result_for(
        plan_path,
        valid,
        issues,
        in_place=args.in_place,
        dry_run=args.dry_run,
        force=args.force,
        slides=generated,
        production_prompts_materialized=bool(args.in_place and not args.dry_run and valid),
    )
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
