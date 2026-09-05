"""Second-generation reference-derived replay layouts.

These builders are intentionally tied to frozen visual references. They keep
formal text, tables, progress bars, panels and decorative marks as native PPT
objects so visual improvement never trades away editability.
"""
from __future__ import annotations


def _table(h, slide, object_id, x, y, w, hgt, rows, *, merges=None, widths=None, heights=None,
           header_fill="#073E78", header_size=8.2, body_size=7.8, rich=False):
    h.add_table(
        slide, object_id, x, y, w, hgt, rows,
        merges=merges or [], rich=rich, header_fill=header_fill,
        body_fill="#FFFFFF", column_widths=widths or [], row_heights=heights or [],
    )
    table = slide["tables"][-1]
    table["border"] = {"all": {"color": "#8FA6C5", "width": 0.55}}
    table["cell_margins"] = {"left": 0.016, "right": 0.016, "top": 0.01, "bottom": 0.01}
    table["cell_styles"]["0"] = {
        "fill": header_fill, "color": "#FFFFFF", "bold": True,
        "size": header_size, "align": 2, "valign": "mid",
    }
    for row_index in range(1, len(rows)):
        table["cell_styles"][str(row_index)] = {
            "fill": "#FFFFFF" if row_index % 2 else "#F7F9FC",
            "color": "#0A2B5E", "size": body_size, "align": 2, "valign": "mid",
        }
    return table


def _icon_text(h, slide, object_id, glyph, x, y, w, hgt, *, size=20, color="#073E78"):
    slide["texts"].append(
        h.text(object_id, glyph, x, y, w, hgt, size=size, color=color, bold=True,
               align="center", valign="middle")
    )


def _info_card(h, slide, object_id, x, title, rows, glyphs):
    y, w, height = 0.118, 0.314, 0.342
    slide["groups"].append(h.group(object_id, x, y, w, height, [
        h.shape(f"{object_id}-body", "rounded_rect", 0, 0, 1, 1,
                fill="#FFFFFF", line="#E60012", line_width=0.9),
        h.shape(f"{object_id}-header", "rect", 0, 0, 1, 0.145,
                fill="#E60012", line="#E60012", line_width=0.3),
    ], role="semantic-panel", native_required=True))
    slide["texts"].append(
        h.text(f"{object_id}-title", title, x + 0.012, y + 0.011, w - 0.024, 0.038,
               size=13.6, color="#FFFFFF", bold=True, align="center", valign="middle")
    )

    labels = ["依据", "周期", "结果", "图标"]
    row_h = 0.068
    start_y = y + 0.061
    for index, (label, value, glyph) in enumerate(zip(labels, rows, glyphs)):
        row_y = start_y + index * row_h
        if index:
            slide["shapes"].append(
                h.line(f"{object_id}-row-{index}", x + 0.010, row_y - 0.007,
                       x + w - 0.010, row_y - 0.007, "#A9B9CE", 0.45)
            )
        _icon_text(h, slide, f"{object_id}-icon-{index}", glyph,
                   x + 0.016, row_y + 0.001, 0.045, 0.043,
                   size=20 if index != 2 else 18)
        slide["texts"].append(
            h.text(f"{object_id}-{label}", label, x + 0.062, row_y + 0.003, 0.055, 0.035,
                   size=10.8, color="#073E78", bold=True, align="center", valign="middle")
        )
        slide["shapes"].append(
            h.line(f"{object_id}-v-{index}", x + 0.122, row_y - 0.003,
                   x + 0.122, row_y + 0.049, "#A9B9CE", 0.45)
        )
        slide["texts"].append(
            h.text(f"{object_id}-{label}-value", value, x + 0.132, row_y - 0.001,
                   w - 0.145, 0.051, size=8.5, color="#17233A", valign="middle")
        )


def fttr_policy_layout_v2(case, run_dir, optimized, h):
    deck = h.make_base(case, run_dir)
    deck["theme"].update({
        "text_color": "#102C5A",
        "table_header_fill": "#073E78",
        "table_fill": "#FFFFFF",
        "chart_text_color": "#102C5A",
        "chart_muted_color": "#54657C",
        "chart_grid_color": "#A9BAD1",
    })
    slide = deck["slides"][0]
    slide["shapes"] = [
        h.shape("background", "rect", 0, 0, 1, 1, fill="#FFFCFC"),
        h.shape("header-wash", "rect", 0, 0, 1, 0.112, fill="#FFF4F5"),
    ]
    slide["groups"] = []
    slide["tables"] = []
    slide["charts"] = []
    slide["texts"] = []
    slide["icons"] = []

    # Header, reconstructed from the frozen reference: brand mark + large title + trophy badge.
    slide["texts"].extend([
        h.text("brand-mark", "⌘", 0.017, 0.017, 0.055, 0.066, size=34,
               color="#E60012", bold=True, align="center", valign="middle"),
        h.text("title-fttr", "FTTR", 0.082, 0.018, 0.112, 0.066, size=32,
               color="#E60012", bold=True, valign="middle"),
        h.text("title", "渠道激励政策明白卡", 0.198, 0.015, 0.382, 0.071, size=29,
               color="#0A2B5E", bold=True, valign="middle"),
    ])
    slide["groups"].append(h.group("policy-badge", 0.61, 0.012, 0.374, 0.085, [
        h.shape("policy-badge-outer", "rounded_rect", 0, 0, 1, 1,
                fill="#FFF8F8", line="#E60012", line_width=1.0),
        h.shape("policy-badge-fill", "rounded_rect", 0.018, 0.065, 0.964, 0.82,
                fill="#E60012", line="#E60012", line_width=0.6),
    ], role="semantic-panel", native_required=True))
    _icon_text(h, slide, "policy-badge-star", "★", 0.625, 0.026, 0.045, 0.047,
               size=22, color="#FFFFFF")
    slide["texts"].append(
        h.text("policy-badge-text", "增收有奖｜减收不罚", 0.67, 0.025, 0.292, 0.048,
               size=20.5, color="#FFFFFF", bold=True, align="center", valign="middle")
    )

    _info_card(h, slide, "commission-new", 0.014, "1. 新增装机佣金", [
        "依据FTTR新装订单（含全屋型/基础型）实际竣工且通过验收的工单数据",
        "订单竣工验收次月起计提，连续计提12个月",
        "按服务费标准计提佣金，直接计入渠道收益",
        "装机越多，收益越高",
    ], ["▤", "▦", "◎", "↗"])
    _info_card(h, slide, "commission-stock", 0.343, "2. 存量维系佣金", [
        "依据FTTR存量在网用户（≥90天）的有效在网与业务状态数据",
        "按自然月计提，次月结算，持续稳定在网持续享受",
        "在网越稳定，计提越持续；长期维系，收益可观",
        "存量稳住，收益长久",
    ], ["▤", "▦", "◎", "◇"])
    _info_card(h, slide, "commission-upgrade", 0.672, "3. 升档提速佣金", [
        "依据FTTR用户宽带升档（带宽提升）或叠加高价值业务的生效数据",
        "升档/生效次月起计提，连续计提6个月",
        "按服务费标准计提佣金，促进价值提升共享收益",
        "价值越高，收益越高",
    ], ["▤", "▦", "◎", "↗"])

    # Full-width policy divider with edge marks.
    slide["shapes"].append(
        h.shape("policy-divider", "rounded_rect", 0.014, 0.468, 0.972, 0.039, fill="#E60012")
    )
    slide["texts"].extend([
        h.text("policy-divider-left", "◇━━", 0.026, 0.474, 0.12, 0.025,
               size=8.5, color="#FFFFFF", bold=True, valign="middle"),
        h.text("policy-divider-text", "激励政策长期稳定执行，增收有奖，减收不罚，携手共赢！",
               0.24, 0.472, 0.52, 0.028, size=12.6, color="#FFFFFF", bold=True,
               align="center", valign="middle"),
        h.text("policy-divider-right", "━━◇", 0.855, 0.474, 0.12, 0.025,
               size=8.5, color="#FFFFFF", bold=True, align="right", valign="middle"),
    ])

    # Bottom title tabs.
    slide["groups"].extend([
        h.group("policy-table-tab", 0.014, 0.516, 0.276, 0.045, [
            h.shape("policy-table-tab-fill", "rounded_rect", 0, 0, 1, 1, fill="#073E78")
        ], role="semantic-panel", native_required=True),
        h.group("subsidy-table-tab", 0.505, 0.516, 0.258, 0.045, [
            h.shape("subsidy-table-tab-fill", "rounded_rect", 0, 0, 1, 1, fill="#073E78")
        ], role="semantic-panel", native_required=True),
    ])
    slide["texts"].extend([
        h.text("policy-table-tab-icon", "▤", 0.027, 0.523, 0.027, 0.028,
               size=13, color="#FFFFFF", bold=True, align="center", valign="middle"),
        h.text("policy-table-tab-text", "一、FTTR渠道佣金计提政策表", 0.057, 0.522, 0.223, 0.028,
               size=11.2, color="#FFFFFF", bold=True, valign="middle"),
        h.text("subsidy-table-tab-icon", "◇", 0.518, 0.522, 0.027, 0.028,
               size=13, color="#FFFFFF", bold=True, align="center", valign="middle"),
        h.text("subsidy-table-tab-text", "二、月度发展达量补贴表", 0.548, 0.522, 0.205, 0.028,
               size=11.2, color="#FFFFFF", bold=True, valign="middle"),
        h.text("subsidy-unit", "（单位：元）", 0.89, 0.523, 0.09, 0.022,
               size=7.8, color="#0A2B5E", align="right", valign="middle"),
    ])

    # Reference has three policy groups (not four). Keep first-column merge topology exact.
    policy_rows = [
        ["场景", "收入变化", "服务费标准", "计提周期"],
        [{"runs": [{"text": "新增装机\n", "bold": True, "size": 8.8}, {"text": "（新装竣工）", "bold": True, "size": 7.5}]},
         {"runs": [{"text": "增收", "color": "#E60012", "bold": True}]},
         {"runs": [{"text": "120元/户/月", "color": "#E60012", "bold": True}]}, "连续计提12个月"],
        ["", "减收", "0元/户/月", "/"],
        [{"runs": [{"text": "存量维系\n", "bold": True, "size": 8.8}, {"text": "（在网≥90天）", "bold": True, "size": 7.5}]},
         {"runs": [{"text": "增收", "color": "#E60012", "bold": True}]},
         {"runs": [{"text": "10元/户/月", "color": "#E60012", "bold": True}]}, "按自然月计提"],
        ["", "减收", "0元/户/月", "/"],
        [{"runs": [{"text": "升档提速\n", "bold": True, "size": 8.8}, {"text": "（带宽升档/加装高价值业务）", "bold": True, "size": 6.7}]},
         {"runs": [{"text": "增收", "color": "#E60012", "bold": True}]},
         {"runs": [{"text": "30元/户/月", "color": "#E60012", "bold": True}]}, "连续计提6个月"],
        ["", "减收", "0元/户/月", "/"],
    ]
    left = _table(
        h, slide, "policy-merged-table", 0.014, 0.558, 0.476, 0.333, policy_rows,
        merges=[[1, 0, 2, 0], [3, 0, 4, 0], [5, 0, 6, 0]],
        widths=[0.13, 0.094, 0.145, 0.107],
        heights=[0.043] + [0.0483] * 6, rich=True, header_size=8.4, body_size=8.0,
    )
    for cell in ("1,1", "1,2", "3,1", "3,2", "5,1", "5,2"):
        left["cell_styles"][cell] = {
            "fill": "#FFFFFF", "color": "#E60012", "bold": True,
            "size": 9.5, "align": 2, "valign": "mid",
        }

    subsidy_rows = [
        [{"runs": [{"text": "达量档位\n", "bold": True, "size": 8.0}, {"text": "（当月FTTR累计竣工户数）", "bold": True, "size": 5.8}]},
         "基础目标", "进阶目标", "挑战目标", "超越目标", "进度达成"],
        ["0~50户（含）", "0", "300", "600", "1,000", "20%"],
        ["51~100户（含）", "500", "1,000", "1,600", "2,500", "45%"],
        ["101~200户（含）", "1,200", "2,200", "3,500", "5,000", "70%"],
        ["201~300户（含）", "2,000", "3,600", "5,500", "8,000", "60%"],
        ["300户以上", "3,000", "5,000", "8,000", "12,000", "85%"],
        [{"runs": [{"text": "本月预计补贴", "color": "#E60012", "bold": True, "size": 8.3},
                    {"text": "（元）", "color": "#E60012", "bold": True, "size": 7.0}]},
         {"runs": [{"text": "1,200", "color": "#E60012", "bold": True}]},
         {"runs": [{"text": "2,200", "color": "#E60012", "bold": True}]},
         {"runs": [{"text": "3,500", "color": "#E60012", "bold": True}]},
         {"runs": [{"text": "5,000", "color": "#E60012", "bold": True}]}, "—"],
    ]
    right = _table(
        h, slide, "monthly-subsidy-table", 0.505, 0.558, 0.48, 0.333, subsidy_rows,
        widths=[0.123, 0.059, 0.059, 0.059, 0.059, 0.121],
        heights=[0.054] + [0.0465] * 5 + [0.0465],
        header_fill="#073E78", header_size=7.2, body_size=7.6, rich=True,
    )
    right["cell_styles"]["6"] = {
        "fill": "#FFF0F2", "color": "#E60012", "bold": True,
        "size": 8.2, "align": 2, "valign": "mid",
    }
    for col in range(1, 5):
        right["cell_styles"][f"6,{col}"] = {
            "fill": "#FFF0F2", "color": "#E60012", "bold": True,
            "size": 9.2, "align": 2, "valign": "mid",
        }

    # Native progress bars overlay the last column; labels remain native table text.
    bar_x = 0.866
    bar_w = 0.066
    percentages = [0.20, 0.45, 0.70, 0.60, 0.85]
    for index, pct in enumerate(percentages):
        y = 0.621 + index * 0.0465
        slide["shapes"].extend([
            h.shape(f"progress-track-{index+1}", "rect", bar_x, y, bar_w, 0.018,
                    fill="#FFFFFF", line="#CBD5E3", line_width=0.4),
            h.shape(f"progress-fill-{index+1}", "rect", bar_x, y, bar_w * pct, 0.018,
                    fill="#2F7DE1", line="#2F7DE1", line_width=0.2),
        ])

    slide["texts"].extend([
        h.text("policy-note", "备注：1. 服务费标准为含税标准；2. 减收不罚，减收部分不扣减历史已计提佣金；3. 具体政策以省公司最新文件为准。",
               0.023, 0.902, 0.46, 0.031, size=6.4, color="#26374F"),
        h.text("subsidy-note", "备注：按月度累计竣工户数达成对应档位，按最高档位补贴标准发放；补贴与佣金可叠加享受。",
               0.518, 0.902, 0.455, 0.031, size=6.4, color="#26374F"),
    ])
    return deck


REFERENCE_BUILDERS_V2 = {
    "native-table-merge-richtext-01": fttr_policy_layout_v2,
}


def build_reference_layout_v2(case, run_dir, optimized, helpers):
    builder = REFERENCE_BUILDERS_V2.get(case.get("case_id"))
    if builder is None:
        return None
    return builder(case, run_dir, optimized, helpers)
