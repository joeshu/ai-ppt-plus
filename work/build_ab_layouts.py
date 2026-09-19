#!/usr/bin/env python3
"""Materialize fresh Knight and PR #40 layouts from the supplied reference.

The two decks intentionally share one semantic reconstruction and one fresh
ImageGen asset set.  The only controlled A/B change is icon placement:
Knight uses the legacy alpha-centroid fit, while PR #40 uses the adaptive
reference-visible fit introduced by the current branch.
"""
from __future__ import annotations

import json
import hashlib
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "ai-ppt-editable" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from asset_placement import adaptive_alpha_fit, alpha_centroid_fit, alpha_geometry  # noqa: E402


W, H = 1536, 864
RED = "#E60012"
DEEP_RED = "#C8102E"
BLACK = "#141414"
GRAY = "#555555"
LIGHT_TEXT = "#6B6B6B"
PALE = "#FFF7F7"
PALE2 = "#FFF1F1"
CARD_LINE = "#F0CCCC"
FONT = "Noto Sans CJK SC"
ASSET_DIR = ROOT / "work" / "lifecycle-ab-20260919" / "assets"
OUT_DIR = ROOT / "work" / "lifecycle-ab-20260919"
IMAGEGEN_SOURCE = {
    "icons": "../../generated_images/exec-d8d33491-8b6f-4148-934c-515eba2c47d8.png",
    "bottom-ribbon-skyline": "../../generated_images/exec-6d9ef3fe-57cb-4a27-a466-9210bc7786a5.png",
    "unicom-knot-mark": "../../generated_images/exec-df8175b1-4913-4c6e-bf6f-ddd38905d448.png",
}


def shape(object_id: str, x: float, y: float, w: float, h: float, *, geometry: str = "rect", fill: str | dict = "none", line: str | dict = "none", rotation: float | None = None, **extra) -> dict:
    value = {"object_id": object_id, "type": geometry, "x": x, "y": y, "w": w, "h": h, "fill": fill, "line": line}
    if rotation is not None:
        value["rotation"] = rotation
    value.update(extra)
    return value


def text(object_id: str, x: float, y: float, w: float, h: float, value: str | None = None, *, runs=None, size: float = 14, color: str = BLACK, bold: bool = False, align: str = "left", valign: str = "top", margin: float = 0, line_spacing: float | None = None, **extra) -> dict:
    spec = {"object_id": object_id, "x": x, "y": y, "w": w, "h": h, "font": FONT, "font_size_pt": size, "color": color, "bold": bold, "align": align, "valign": valign, "margin_left": margin, "margin_right": margin, "margin_top": margin, "margin_bottom": margin, "wrap": "square", "auto_fit": "none"}
    if runs is not None:
        spec["runs"] = runs
    elif value is not None:
        spec["text"] = value
    if line_spacing is not None:
        spec["line_spacing"] = line_spacing
    spec.update(extra)
    return spec


def run(value: str, *, size: float | None = None, color: str | None = None, bold: bool | None = None, font: str = FONT) -> dict:
    item = {"text": value, "font": font}
    if size is not None:
        item["font_size_pt"] = size
    if color is not None:
        item["color"] = color
    if bold is not None:
        item["bold"] = bold
    return item


def icon_path(filename: str) -> str:
    return f"icons/{filename}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Approximate visible icon locks measured from the supplied 1536x864 reference.
# Each lock is an intended visible bbox inside a larger independently movable
# image slot.  The adaptive branch fits the visible alpha to this lock.
ICON_LOCKS = [
    ("current-bar", "icon_r1c1.png", 67, 168, 62, 62, [0.14, 0.16, 0.72, 0.66]),
    ("target", "icon_r1c2.png", 322, 168, 62, 62, [0.13, 0.13, 0.74, 0.74]),
    ("card1-bar", "icon_r1c1.png", 63, 417, 58, 58, [0.18, 0.16, 0.64, 0.67]),
    ("card1-person", "icon_r1c3.png", 145, 416, 55, 55, [0.19, 0.15, 0.62, 0.70]),
    ("card1-gear", "icon_r1c4.png", 145, 466, 55, 55, [0.14, 0.14, 0.72, 0.72]),
    ("card1-group", "icon_r2c1.png", 62, 515, 60, 60, [0.11, 0.17, 0.78, 0.58]),
    ("card1-trend", "icon_r3c2.png", 64, 612, 60, 60, [0.12, 0.18, 0.76, 0.62]),
    ("card2-person", "icon_r1c3.png", 574, 416, 55, 55, [0.19, 0.15, 0.62, 0.70]),
    ("card2-phone", "icon_r2c2.png", 574, 466, 55, 55, [0.18, 0.14, 0.66, 0.72]),
    ("card2-list", "icon_r2c3.png", 574, 516, 55, 55, [0.13, 0.15, 0.74, 0.70]),
    ("card2-heart", "icon_r2c4.png", 574, 612, 60, 60, [0.12, 0.16, 0.76, 0.68]),
    ("card3-group", "icon_r2c1.png", 1080, 416, 60, 60, [0.10, 0.17, 0.80, 0.58]),
    ("card3-coins", "icon_r3c1.png", 1080, 466, 60, 60, [0.10, 0.22, 0.80, 0.58]),
    ("card3-bar", "icon_r1c1.png", 1080, 516, 60, 60, [0.15, 0.16, 0.70, 0.65]),
    ("card3-link", "icon_r3c3.png", 1080, 612, 60, 60, [0.12, 0.13, 0.76, 0.74]),
    ("management-shield", "icon_r3c4.png", 607, 684, 58, 42, [0.18, 0.10, 0.64, 0.78]),
    ("management-doc", "icon_r4c1.png", 1002, 684, 58, 42, [0.18, 0.10, 0.64, 0.78]),
    ("outcome-bar", "icon_r1c1.png", 274, 748, 58, 50, [0.14, 0.14, 0.72, 0.70]),
    ("outcome-shield", "icon_r3c4.png", 592, 748, 58, 50, [0.18, 0.08, 0.64, 0.84]),
    ("outcome-group", "icon_r2c1.png", 932, 748, 58, 50, [0.10, 0.16, 0.80, 0.62]),
    ("outcome-target", "icon_r1c2.png", 1260, 746, 65, 54, [0.12, 0.10, 0.76, 0.78]),
]


def asset_placement(variant: str, filename: str, slot: tuple[int, int, int, int], target_bbox: list[float]) -> tuple[tuple[int, int, int, int], dict]:
    path = ASSET_DIR / "icons" / filename
    if variant == "pr40":
        placed, evidence = adaptive_alpha_fit(path, *slot, reference_visible_bbox_norm=target_bbox, return_evidence=True)
        return placed, {"mode": "reference-visible-fit", **evidence, "reference_visible_bbox_norm": target_bbox}
    placed = alpha_centroid_fit(path, *slot, contain=1.0)
    geometry = alpha_geometry(path)
    px, py, pw, ph = placed
    x, y, w, h = slot
    vx, vy, vw, vh = geometry["visible_bbox_px"]
    sx, sy = pw / geometry["canvas_px"][0], ph / geometry["canvas_px"][1]
    visible = [px + vx * sx, py + vy * sy, vw * sx, vh * sy]
    centroid = [px + geometry["visible_centroid_px"][0] * sx, py + geometry["visible_centroid_px"][1] * sy]
    return placed, {"mode": "alpha-centroid-fit", "slot_bbox": list(slot), "placement_bbox": list(placed), "placed_visible_bbox": visible, "placed_visible_centroid": centroid, "reference_visible_bbox_norm": target_bbox}


def build(variant: str) -> tuple[dict, dict]:
    shapes: list[dict] = []
    texts: list[dict] = []
    icons: list[dict] = []
    placement_evidence: list[dict] = []

    # Header, native text, and simple geometry.
    shapes.extend([
        shape("header-slash-1", 30, 21, 16, 44, geometry="parallelogram", fill=RED, line="none", rotation=-12),
        shape("header-slash-2", 52, 21, 16, 44, geometry="parallelogram", fill=RED, line="none", rotation=-12),
    ])
    texts.append(text("title", 86, 12, 1040, 54, runs=[run("聚焦流失三大根因，构建", size=26, color=BLACK, bold=True), run("全生命周期客户运营体系", size=26, color=RED, bold=True)], valign="middle"))
    texts.append(text("subtitle", 94, 70, 1040, 34, runs=[run("主动干预", size=17, color=BLACK, bold=True), run(" · ", size=17, color=RED, bold=True), run("强化挽留", size=17, color=BLACK, bold=True), run(" · ", size=17, color=RED, bold=True), run("前置维系", size=17, color=BLACK, bold=True), run("，推动流失收入持续压降", size=17, color=BLACK, bold=False)], valign="middle"))

    # Top right logo: generated mark plus editable brand text.
    logo_slot = (1318, 14, 53, 53)
    logo_target = [0.10, 0.10, 0.80, 0.80]
    logo_placed, logo_ev = asset_placement(variant, "../generated/unicom-knot-mark.png", logo_slot, logo_target) if False else (None, None)
    # The logo mark lives outside the icon folder, so keep its placement math local.
    logo_path = ASSET_DIR / "generated" / "unicom-knot-mark.png"
    if variant == "pr40":
        logo_placed, logo_ev = adaptive_alpha_fit(logo_path, *logo_slot, reference_visible_bbox_norm=logo_target, return_evidence=True)
        logo_ev = {"object_id": "unicom-knot-mark", "mode": "reference-visible-fit", **logo_ev, "reference_visible_bbox_norm": logo_target}
    else:
        logo_placed = alpha_centroid_fit(logo_path, *logo_slot, contain=1.0)
        logo_ev = {"object_id": "unicom-knot-mark", "mode": "alpha-centroid-fit", "slot_bbox": list(logo_slot), "placement_bbox": list(logo_placed), "reference_visible_bbox_norm": logo_target}
    icons.append({"object_id": "unicom-knot-mark", "file": "generated/unicom-knot-mark.png", "x": logo_placed[0], "y": logo_placed[1], "w": logo_placed[2], "h": logo_placed[3], "fit": "contain", "alt_text": "独立可移动联通红色结形标志"})
    placement_evidence.append(logo_ev)
    texts.extend([
        text("unicom-cn", 1378, 13, 135, 32, "中国联通", size=16, color=BLACK, bold=True, valign="middle"),
        text("unicom-en", 1379, 43, 125, 16, "china unicom", size=10, color=BLACK, bold=True, valign="middle"),
        text("unicom-slogan", 1377, 59, 143, 17, "创新 · 与智慧同行", size=7, color=LIGHT_TEXT, align="center", valign="middle"),
    ])

    # Current/target pair.
    shapes.extend([
        shape("status-container", 29, 128, 486, 204, geometry="roundRect", fill="#FFFDFD", line={"color": CARD_LINE, "width": 1}),
        shape("status-current", 43, 148, 191, 154, geometry="roundRect", fill=PALE2, line="none"),
        shape("status-target", 295, 148, 216, 154, geometry="roundRect", fill=PALE2, line="none"),
        shape("status-arrow-1", 245, 199, 20, 25, geometry="rightArrow", fill=RED, line="none"),
        shape("status-arrow-2", 263, 199, 20, 25, geometry="rightArrow", fill=RED, line="none"),
    ])
    texts.extend([
        text("status-current-label", 96, 161, 94, 34, "现状", size=17, color=RED, bold=True, align="center", valign="middle"),
        text("status-current-value", 56, 208, 162, 68, "趋势向好\n仍在高位", size=16, color=BLACK, bold=True, align="center", valign="middle", line_spacing=1.12),
        text("status-target-label", 350, 161, 94, 34, "目标", size=17, color=RED, bold=True, align="center", valign="middle"),
        text("status-target-value-main", 310, 208, 146, 58, "流失收入\n持续压降", size=14, color=BLACK, bold=True, align="center", valign="middle", line_spacing=1.12),
        text("status-target-value-percent", 440, 239, 68, 58, "10%", size=19, color=RED, bold=True, align="center", valign="middle"),
    ])

    # Native line chart and surrounding labels.
    shapes.append(shape("chart-title-pill", 534, 132, 290, 39, geometry="roundRect", fill=RED, line="none"))
    texts.append(text("chart-title", 548, 136, 262, 52, "出账流失收入（单位：万元）", size=13.5, color="#FFFFFF", bold=True, valign="middle"))
    shapes.append(shape("chart-outline", 575, 188, 917, 115, geometry="rect", fill="#FFFFFF/0", line={"color": "#E7E7E7", "width": 0.6}))
    chart = {
        "object_id": "loss-income-chart",
        "type": "line",
        "x": 575, "y": 188, "w": 917, "h": 115,
        "title": None,
        "categories": [f"{i}月" for i in range(1, 13)],
        "series": [
            {"name": "2025年", "values": [218.9, 222.5, 253.3, 254.6, 290.3, 315.0, 332.8, 232.9, 236.0, 230.0, 221.7, 213.9, 265.5], "fill": "#1673D1", "line": {"style": "solid", "fill": "#1673D1", "width": 1}},
            {"name": "2026年", "values": [218.9, 230.3, 220.8, 248.3, 232.7, 243.2, 224.0, None, None, None, None, None, None], "fill": RED, "line": {"style": "solid", "fill": RED, "width": 1}},
        ],
        "legend": True,
        "display_blanks_as": "gap",
        "x_axis": {"textStyle": {"fontSize": 10, "fill": "#555555"}, "majorGridlines": None},
        "y_axis": {"min": 150, "max": 450, "majorUnit": 100, "textStyle": {"fontSize": 10, "fill": "#555555"}, "majorGridlines": {"style": "solid", "fill": "#E6E6E6", "width": 0.5}},
    }
    charts = [chart]
    texts.append(text("chart-target-pill", 1268, 169, 212, 36, "目标：持续压降10% ↓", size=12, color=RED, bold=True, align="center", valign="middle"))
    shapes.append(shape("chart-target-pill-outline", 1268, 169, 212, 36, geometry="roundRect", fill="#FFFFFF/0", line={"color": RED, "width": 0.8}))
    # Keep chart value labels native and independent from the chart object.
    blue = [218.9, 222.5, 253.3, 254.6, 290.3, 315.0, 332.8, 232.9, 236.0, 230.0, 221.7, 213.9, 265.5]
    red = [218.9, 230.3, 220.8, 248.3, 232.7, 243.2, 224.0]
    plot_x, plot_w = 601, 850
    for index, value in enumerate(blue):
        x = plot_x + index * (plot_w / 12) - 15
        y = 218 - (value - 150) / 300 * 74
        texts.append(text(f"chart-blue-value-{index+1}", x, y - 17, 33, 13, f"{value:.1f}", size=7.2, color="#1673D1", bold=True, align="center", valign="middle"))
    for index, value in enumerate(red):
        x = plot_x + index * (plot_w / 12) - 15
        y = 218 - (value - 150) / 300 * 74
        texts.append(text(f"chart-red-value-{index+1}", x, y + 5, 33, 13, f"{value:.1f}", size=7.2, color=RED, bold=True, align="center", valign="middle"))

    # Three main cards.
    cards = [
        ("card1", 30, 347, 487, "01", "发展质量", "主动干预", "端网业适配", "#FFFFFF"),
        ("card2", 535, 347, 482, "02", "满卡满融", "强化挽留", "拆机挽留", "#FFFFFF"),
        ("card3", 1039, 347, 468, "03", "事后回捞", "前置维系", "新入网&金融维系", "#FFFFFF"),
    ]
    for cid, x, y, w, no, title, subtitle, subtag, body_fill in cards:
        shapes.extend([
            shape(f"{cid}-body", x, y + 57, w, 264, geometry="roundRect", fill=body_fill, line={"color": CARD_LINE, "width": 1}),
            shape(f"{cid}-header", x, y, w, 58, geometry="roundRect", fill=RED, line="none"),
        ])
        header_height = 64 if cid == "card3" else 48
        texts.append(text(f"{cid}-header-text", x + 18, y + 2, w - 36, header_height, f"{no}  {title}  |  {subtitle}（{subtag}）", size=14, color="#FFFFFF", bold=True, valign="middle"))

    # Body text. Keep list/card semantics as repeated native text boxes, not tables.
    texts.extend([
        text("card1-goal", 204, 412, 286, 30, runs=[run("目标用户：", size=13.5, color=BLACK, bold=True), run("40万", size=13.5, color=BLACK, bold=False)], valign="middle"),
        text("card1-adapt", 204, 444, 290, 84, "套餐适配＋ FTTR / 5G光猫，\n次推优选千兆、CBSS弹窗拦截", size=12.5, color=BLACK, bold=True, line_spacing=1.15),
        text("card1-org", 204, 514, 292, 98, "营销组织：智客结对协同营销，\nOMO触达（到厅、看弹窗、看推荐）", size=12.5, color=BLACK, bold=True, line_spacing=1.15),
        text("card1-bottom", 70, 617, 400, 43, "提升匹配度，降低流失风险", size=15.5, color=RED, bold=True, align="center", valign="middle"),
        text("card2-goal", 713, 412, 270, 30, runs=[run("目标用户：", size=13.5, color=BLACK, bold=True), run("20万", size=13.5, color=BLACK, bold=False)], valign="middle"),
        text("card2-scene", 713, 444, 285, 92, "发展场景：①外呼越商同时推荐搭载，\n②触达对派单，③前期已发展用户\n④到厅用户—看弹窗", size=9.7, color=BLACK, bold=True, line_spacing=1.15),
        text("card2-action", 713, 526, 286, 96, "举措：三抓（挖需求、搭载、降套）\n三换（装老门、方案升级、问题解决）\n中台拆机：挖真实需求，定制挽留方案", size=9.5, color=BLACK, bold=True, line_spacing=1.12),
        text("card2-bottom", 582, 617, 390, 43, "深挖需求，提升价值与粘性", size=15.5, color=RED, bold=True, align="center", valign="middle"),
        text("card3-new", 1146, 411, 329, 84, "新入网维系：\n发展主动联系用户，做关爱提醒，\n到厅充值送小礼品，促二次保长期在网", size=10.0, color=BLACK, bold=True, line_spacing=1.12),
        text("card3-finance", 1146, 494, 329, 64, "金融维系：\n回访、包装价值是否足额，促进实发展", size=10.0, color=BLACK, bold=True, line_spacing=1.12),
        text("card3-monitor", 1146, 553, 329, 84, "分类分级监控：\n按入网时长、套餐种类、客户价值分类，\n识别风险客群并前置维系。", size=10.0, color=BLACK, bold=True, line_spacing=1.12),
        text("card3-bottom", 1090, 617, 384, 43, "前置服务，延长在网生命周期", size=15.5, color=RED, bold=True, align="center", valign="middle"),
    ])
    # Soft bottom callout fills in the cards.
    shapes.extend([
        shape("card1-bottom-fill", 45, 608, 457, 53, geometry="roundRect", fill="#FFEFEF", line="none"),
        shape("card2-bottom-fill", 550, 608, 452, 53, geometry="roundRect", fill="#FFEFEF", line="none"),
        shape("card3-bottom-fill", 1054, 608, 438, 53, geometry="roundRect", fill="#FFEFEF", line="none"),
    ])

    # Management band.
    shapes.append(shape("management-band", 30, 679, 1476, 56, geometry="roundRect", fill="#FFFDFD", line={"color": RED, "width": 0.8}))
    texts.extend([
        text("management-title", 55, 682, 520, 54, "管理保障  |  借鉴郑州经验，营造高质量发展氛围", size=12.5, color=RED, bold=True, valign="middle"),
        text("management-rule1", 685, 682, 316, 54, "① 建立一线员工信誉分管理体系", size=11.5, color=BLACK, bold=True, valign="middle"),
        text("management-rule2", 1064, 682, 414, 54, "② 明确违反生产经营管理秩序行为处理标准", size=10.5, color=BLACK, bold=True, valign="middle"),
    ])
    shapes.extend([
        shape("management-divider-1", 650, 681, 1, 52, geometry="rect", fill="#F4B9B9", line="none"),
        shape("management-divider-2", 1034, 681, 1, 52, geometry="rect", fill="#F4B9B9", line="none"),
    ])

    # Outcome strip. It stays native/editable above the generated bottom band.
    shapes.extend([
        shape("outcomes-strip", 30, 741, 1476, 80, geometry="roundRect", fill="#FFFDFD", line={"color": CARD_LINE, "width": 0.8}),
        shape("outcomes-title", 30, 741, 240, 80, geometry="parallelogram", fill=RED, line="none"),
        shape("outcome-card-1", 270, 741, 287, 80, geometry="roundRect", fill="#FFF7F7", line="none"),
        shape("outcome-card-2", 602, 741, 287, 80, geometry="roundRect", fill="#FFF7F7", line="none"),
        shape("outcome-card-3", 934, 741, 287, 80, geometry="roundRect", fill="#FFF7F7", line="none"),
        shape("outcome-card-4", 1266, 741, 240, 80, geometry="roundRect", fill="#FFF7F7", line="none"),
        shape("outcome-arrow-1", 558, 771, 30, 24, geometry="rightArrow", fill=RED, line="none"),
        shape("outcome-arrow-2", 890, 771, 30, 24, geometry="rightArrow", fill=RED, line="none"),
        shape("outcome-arrow-3", 1222, 771, 30, 24, geometry="rightArrow", fill=RED, line="none"),
    ])
    texts.extend([
        text("outcomes-title-text", 52, 759, 166, 43, "预期成效", size=20, color="#FFFFFF", bold=True, valign="middle"),
        text("outcome-1-text", 340, 754, 178, 48, "高质量发展\n提升收入持续性", size=12.5, color=BLACK, bold=True, valign="middle", line_spacing=1.12),
        text("outcome-2-text", 672, 754, 184, 48, "降低流失风险\n减少非必要流失", size=12.5, color=BLACK, bold=True, valign="middle", line_spacing=1.12),
        text("outcome-3-text", 1004, 754, 184, 48, "客户价值提升\nARPU与粘性增长", size=12.5, color=BLACK, bold=True, valign="middle", line_spacing=1.12),
        text("outcome-4-text", 1340, 750, 156, 62, "流失收入\n持续压降\n目标 10%", size=10.0, color=RED, bold=True, align="center", valign="middle", line_spacing=1.05),
    ])

    # Generated bottom art; text remains native above it.
    ribbon_path = ASSET_DIR / "generated" / "bottom-ribbon-skyline.png"
    ribbon_geom = alpha_geometry(ribbon_path)
    icons.append({"object_id": "bottom-ribbon-skyline", "file": "generated/bottom-ribbon-skyline.png", "x": 0, "y": 804, "w": 1536, "h": 200, "fit": "contain", "alt_text": "独立可移动红色飘带与城市剪影视觉资产", "allow_bleed": True})
    texts.extend([
        text("footer-left", 27, 821, 330, 30, "联通世界  创享美好智慧生活", size=12.5, color="#8D8D8D", bold=False, valign="middle"),
        text("footer-5g", 1435, 825, 70, 30, "5Gⁿ", size=13, color=RED, bold=True, align="center", valign="middle"),
    ])

    # Icon hosts are native pale circles; icons remain independent pictures.
    for x, y, w, h in [(67, 168, 62, 62), (322, 168, 62, 62), (63, 417, 58, 58), (145, 416, 55, 55), (145, 466, 55, 55), (62, 515, 60, 60), (64, 612, 60, 60), (574, 416, 55, 55), (574, 466, 55, 55), (574, 516, 55, 55), (574, 612, 60, 60), (1080, 416, 60, 60), (1080, 466, 60, 60), (1080, 516, 60, 60), (1080, 612, 60, 60)]:
        shapes.append(shape(f"icon-host-{x}-{y}", x, y, w, h, geometry="ellipse", fill="#FFF4F4", line="none"))

    for object_id, filename, x, y, w, h, target_bbox in ICON_LOCKS:
        slot = (x, y, w, h)
        placed, evidence = asset_placement(variant, filename, slot, target_bbox)
        icons.append({"object_id": object_id, "file": icon_path(filename), "x": placed[0], "y": placed[1], "w": placed[2], "h": placed[3], "fit": "contain", "alt_text": f"独立可移动红色图标 {object_id}"})
        evidence["object_id"] = object_id
        placement_evidence.append(evidence)

    # Header and final layer order: native containers first, then generated
    # visuals, then editable text boxes.  The Artifact Tool preserves array
    # order within each object category, and the evaluator audits the result.
    deck = {
        "schema": "ai-ppt-plus/layout/v3",
        "units": "px",
        "ref_width": W,
        "ref_height": H,
        "slide_width_px": W,
        "slide_height_px": H,
        "slide_width_in": 13.333333,
        "slide_height_in": 7.5,
        "assets_dir": str(ASSET_DIR),
        "font_family": FONT,
        "background_fill": "#FFFFFF",
        "strict_input": True,
        "editable_object_policy": "native-semantic-objects",
        "theme": {"font": FONT, "text_color": BLACK},
        "slides": [{"background_fill": "#FFFFFF", "shapes": shapes, "charts": charts, "icons": icons, "texts": texts, "speaker_notes": f"Fresh 2026-09-19 five-axis benchmark deck: {variant}. Source SHA-256 75077f148156d6424c87d826d65da6403c529b5a36c519a20d37d49773b77021. Knight baseline and PR #40 candidate share the same reference and native semantic layout; only icon placement policy differs."}],
    }
    evidence = {
        "schema": "ai-ppt-plus/placement-evidence/v1",
        "variant": variant,
        "source_sha256": "75077f148156d6424c87d826d65da6403c529b5a36c519a20d37d49773b77021",
        "canvas_px": [W, H],
        "canvas_in": [13.333333, 7.5],
        "placement_policy": "adaptive-alpha-fit+reference-visible-fit" if variant == "pr40" else "alpha-centroid-fit",
        "assets": placement_evidence,
    }
    return deck, evidence


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for variant in ("knight", "pr40"):
        deck, evidence = build(variant)
        (OUT_DIR / f"{variant}.layout.json").write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (OUT_DIR / f"{variant}.placement-evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        icon_by_id = {item["object_id"]: item for item in deck["slides"][0]["icons"]}
        geometry_assets = []
        for placement in evidence["assets"]:
            item = icon_by_id.get(placement["object_id"])
            if not item or "reference_visible_bbox_norm" not in placement:
                continue
            x, y, w, h = placement["slot_bbox"]
            rx, ry, rw, rh = placement["reference_visible_bbox_norm"]
            geometry_assets.append({
                "object_id": placement["object_id"],
                "file": item["file"],
                "x": item["x"], "y": item["y"], "w": item["w"], "h": item["h"],
                "visual_lock_bbox": [x + rx * w, y + ry * h, rw * w, rh * h],
            })
        (OUT_DIR / f"{variant}-icon-geometry.json").write_text(
            json.dumps({"schema": "ai-ppt-plus/alpha-geometry-manifest/v1", "assets": geometry_assets}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    inventory = {
        "schema": "ai-ppt-plus/visual-inventory/v1",
        "source": {"path": "reference/reference.jpeg", "sha256": "75077f148156d6424c87d826d65da6403c529b5a36c519a20d37d49773b77021", "size_px": [W, H]},
        "slide_count": 1,
        "slide_size_in": [13.333333, 7.5],
        "major_regions": [
            {"id": "header", "bbox_px": [0, 0, 1536, 118], "kind": "native_text_and_brand_asset"},
            {"id": "status-and-chart", "bbox_px": [29, 128, 1478, 204], "kind": "native_cards_and_chart"},
            {"id": "three-strategy-cards", "bbox_px": [30, 347, 1477, 321], "kind": "native_repeated_component_group"},
            {"id": "management-band", "bbox_px": [30, 679, 1476, 56], "kind": "native_panel"},
            {"id": "outcomes-strip", "bbox_px": [30, 741, 1476, 80], "kind": "native_repeated_component_group"},
            {"id": "bottom-ribbon", "bbox_px": [0, 804, 1536, 60], "kind": "imagegen_asset"},
        ],
        "object_counts": {"native_text_slots": 74, "native_shapes": 57, "native_charts": 1, "independent_image_assets": len(ICON_LOCKS) + 2},
        "semantic_rules": {"three_cards_are_repeated_components_not_table": True, "formal_text_native": True, "whole_slide_picture": False},
    }
    (OUT_DIR / "visual-inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prompt_file = OUT_DIR / "prompts" / "imagegen-assets.md"
    imagegen_assets = []
    for path in sorted((ASSET_DIR / "icons").glob("*.png")):
        imagegen_assets.append({
            "asset_id": path.stem,
            "asset_class": "icon",
            "provenance_mode": "imagegen",
            "generated_source": IMAGEGEN_SOURCE["icons"],
            "copied_to": f"assets/icons/{path.name}",
            "sha256": file_sha256(path),
            "layer": "icons",
            "prompt_file": "prompts/imagegen-assets.md",
            "backend": "OpenAI ImageGen",
            "background_mode": "transparent",
            "fallback_level": "direct-alpha",
            "canonical_asset": True,
            "qa_preview_only": False,
            "cache_key": file_sha256(path),
        })
    for asset_id, filename in (("unicom-knot-mark", "unicom-knot-mark.png"), ("bottom-ribbon-skyline", "bottom-ribbon-skyline.png")):
        path = ASSET_DIR / "generated" / filename
        imagegen_assets.append({
            "asset_id": asset_id,
            "asset_class": "decorative_art",
            "provenance_mode": "imagegen",
            "generated_source": IMAGEGEN_SOURCE[asset_id],
            "copied_to": f"assets/generated/{filename}",
            "sha256": file_sha256(path),
            "layer": "icons",
            "prompt_file": "prompts/imagegen-assets.md",
            "backend": "OpenAI ImageGen",
            "background_mode": "transparent",
            "fallback_level": "direct-alpha",
            "canonical_asset": True,
            "qa_preview_only": False,
            "cache_key": file_sha256(path),
        })
    imagegen_manifest = {
        "schema": "ai-ppt-plus/imagegen-assets-manifest/v1",
        "request_id": "lifecycle-ab-20260919-fresh-imagegen",
        "provenance_mode": "imagegen",
        "asset_generation_policy": "transparent_first_v1",
        "generation_accounting": {
            "billable_generation_calls": 3,
            "billable_transparent_edit_calls": 0,
            "local_derivative_count": 16,
            "qa_preview_count": 1,
            "full_sheet_retries": 0,
            "single_asset_retries": 0,
        },
        "assets": imagegen_assets,
    }
    (OUT_DIR / "imagegen-assets-manifest.json").write_text(json.dumps(imagegen_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
