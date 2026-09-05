"""Reference-derived native layouts for replay cases whose generic templates are visually invalid.

These builders intentionally encode the visible reference structure with native
PowerPoint objects. They are regression fixtures for the image-reconstruction
path, not new production templates.
"""
from __future__ import annotations


def _light_table(h, slide, object_id, x, y, w, hgt, rows, *, merges=None, widths=None, heights=None, header_fill="#063C76", header_size=8.5, body_size=8.0, rich=False):
    h.add_table(slide, object_id, x, y, w, hgt, rows, merges=merges, rich=rich, header_fill=header_fill,
                body_fill="#FFFDFD", column_widths=widths, row_heights=heights)
    table = slide["tables"][-1]
    table["border"] = {"all": {"color": "#9EB2CD", "width": 0.65}}
    table["cell_margins"] = {"left": 0.025, "right": 0.025, "top": 0.016, "bottom": 0.016}
    table["cell_styles"]["0"] = {"fill": header_fill, "color": "#FFFFFF", "bold": True, "size": header_size, "align": "center", "valign": "mid"}
    for row_index in range(1, len(rows)):
        table["cell_styles"][str(row_index)] = {
            "fill": "#FFFFFF" if row_index % 2 else "#F8FAFD",
            "color": "#0A2B5E", "size": body_size, "align": "center", "valign": "mid"
        }
    return table


def _info_card(h, slide, object_id, x, title, rows):
    y, w, height = 0.108, 0.314, 0.315
    slide["groups"].append(h.group(object_id, x, y, w, height, [
        h.shape(f"{object_id}-body", "rounded_rect", 0, 0, 1, 1, fill="#FFFFFF", line="#E60012", line_width=1.0),
        h.shape(f"{object_id}-header", "rect", 0, 0, 1, 0.155, fill="#E60012"),
    ], role="semantic-panel", native_required=True))
    slide["texts"].append(h.text(f"{object_id}-title", title, x + 0.012, y + 0.012, w - 0.024, 0.037,
                                 size=12.5, color="#FFFFFF", bold=True, align="center", valign="mid"))
    labels = ["依据", "周期", "结果", "目标"]
    for index, (label, value) in enumerate(zip(labels, rows)):
        row_y = y + 0.065 + index * 0.061
        if index:
            slide["shapes"].append(h.line(f"{object_id}-row-{index}", x + 0.012, row_y - 0.006, x + w - 0.012, row_y - 0.006, "#B7C5D8", 0.55))
        slide["texts"].append(h.text(f"{object_id}-{label}", label, x + 0.018, row_y, 0.075, 0.032,
                                     size=9.4, color="#073A75", bold=True, align="center", valign="mid"))
        slide["shapes"].append(h.line(f"{object_id}-v-{index}", x + 0.105, row_y - 0.004, x + 0.105, row_y + 0.041, "#B7C5D8", 0.55))
        slide["texts"].append(h.text(f"{object_id}-{label}-value", value, x + 0.118, row_y - 0.001, w - 0.136, 0.043,
                                     size=7.8, color="#17233A", bold=False, valign="mid"))


def fttr_policy_layout(case, run_dir, optimized, h):
    """Rebuild the visible FTTR policy-card reference instead of the old dark generic template."""
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
        h.shape("background", "rect", 0, 0, 1, 1, fill="#FFF9FA"),
        h.shape("header-wash", "rect", 0, 0, 1, 0.105, fill="#FFF1F3"),
    ]
    slide["groups"] = []
    slide["tables"] = []
    slide["charts"] = []
    slide["texts"] = []
    slide["icons"] = []

    # Header: large two-tone title and policy badge.
    slide["texts"].extend([
        h.text("brand-mark", "◆", 0.016, 0.027, 0.05, 0.05, size=25, color="#E60012", bold=True, align="center", valign="mid"),
        h.text("title-fttr", "FTTR", 0.075, 0.021, 0.115, 0.063, size=30, color="#E60012", bold=True, valign="mid"),
        h.text("title", "渠道激励政策明白卡", 0.185, 0.018, 0.385, 0.068, size=27, color="#0A2B5E", bold=True, valign="mid"),
    ])
    slide["groups"].append(h.group("policy-badge", 0.615, 0.012, 0.365, 0.078, [
        h.shape("policy-badge-fill", "rounded_rect", 0, 0, 1, 1, fill="#E60012", line="#E60012", line_width=0.8),
    ], role="semantic-panel", native_required=True))
    slide["texts"].append(h.text("policy-badge-text", "增收有奖｜减收不罚", 0.63, 0.027, 0.335, 0.045,
                                 size=19, color="#FFFFFF", bold=True, align="center", valign="mid"))

    _info_card(h, slide, "commission-new", 0.015, "1. 新增装机佣金", [
        "依据FTTR新装订单及工单数据",
        "竣工次月起计提，连续计提12个月",
        "按服务费标准计提佣金",
        "装机越多，收益越高",
    ])
    _info_card(h, slide, "commission-stock", 0.343, "2. 存量维系佣金", [
        "依据FTTR存量在网用户业务状态数据",
        "按自然月计提，次月结算",
        "在网越稳定，计提越持续",
        "存量稳住，收益长久",
    ])
    _info_card(h, slide, "commission-upgrade", 0.671, "3. 升档提速佣金", [
        "依据FTTR用户宽带升档生效数据",
        "升档生效次月起计提，连续计提6个月",
        "按服务费标准计提佣金",
        "价值越高，收益越高",
    ])

    # Red policy divider.
    slide["shapes"].append(h.shape("policy-divider", "rounded_rect", 0.015, 0.432, 0.97, 0.035, fill="#E60012"))
    slide["texts"].append(h.text("policy-divider-text", "激励政策长期稳定执行，增收有奖，减收不罚，携手共赢！",
                                 0.08, 0.437, 0.84, 0.025, size=11.5, color="#FFFFFF", bold=True, align="center", valign="mid"))

    # Section tabs.
    slide["groups"].extend([
        h.group("policy-table-tab", 0.015, 0.477, 0.27, 0.041, [h.shape("policy-table-tab-fill", "rounded_rect", 0, 0, 1, 1, fill="#073E78")]),
        h.group("subsidy-table-tab", 0.505, 0.477, 0.25, 0.041, [h.shape("subsidy-table-tab-fill", "rounded_rect", 0, 0, 1, 1, fill="#073E78")]),
    ])
    slide["texts"].extend([
        h.text("policy-table-tab-text", "一、FTTR渠道佣金计提政策表", 0.025, 0.485, 0.25, 0.025, size=10.5, color="#FFFFFF", bold=True, valign="mid"),
        h.text("subsidy-table-tab-text", "二、月度发展达量补贴表", 0.515, 0.485, 0.23, 0.025, size=10.5, color="#FFFFFF", bold=True, valign="mid"),
        h.text("subsidy-unit", "（单位：元）", 0.89, 0.486, 0.09, 0.022, size=7.5, color="#0A2B5E", align="right", valign="mid"),
    ])

    policy_rows = [
        ["场景", "收入变化", "服务费标准", "计提周期"],
        ["新增装机\n（新装竣工）", {"runs": [{"text": "增收", "color": "#E60012", "bold": True}]}, {"runs": [{"text": "120元/户/月", "color": "#E60012", "bold": True}]}, "连续计提12个月"],
        ["", "减收", "0元/户/月", "/"],
        ["存量维系\n（在网≥90天）", {"runs": [{"text": "增收", "color": "#E60012", "bold": True}]}, {"runs": [{"text": "10元/户/月", "color": "#E60012", "bold": True}]}, "按自然月计提"],
        ["", "减收", "0元/户/月", "/"],
        ["升档提速\n（带宽升档/加装高价值业务）", {"runs": [{"text": "增收", "color": "#E60012", "bold": True}]}, {"runs": [{"text": "30元/户/月", "color": "#E60012", "bold": True}]}, "连续计提6个月"],
        ["", "减收", "0元/户/月", "/"],
        ["其他场景", "增收", "按政策", "月度"],
        ["", "减收", "0元/户/月", "/"],
    ]
    left = _light_table(h, slide, "policy-merged-table", 0.015, 0.515, 0.475, 0.305, policy_rows,
                        merges=case.get("data", {}).get("merge_spans") or [], widths=[0.13, 0.095, 0.145, 0.105],
                        heights=[0.04] + [0.033] * 8, rich=True)
    for cell in ("1,1", "1,2", "3,1", "3,2", "5,1", "5,2"):
        left["cell_styles"][cell] = {"fill": "#FFFFFF", "color": "#E60012", "bold": True, "size": 9.0, "align": "center", "valign": "mid"}

    subsidy_rows = [
        ["达量档位", "基础目标", "进阶目标", "挑战目标", "超越目标", "进度达成"],
        ["0~50户（含）", "0", "300", "600", "1,000", "20%"],
        ["51~100户（含）", "500", "1,000", "1,600", "2,500", "45%"],
        ["101~200户（含）", "1,200", "2,200", "3,500", "5,000", "70%"],
        ["201~300户（含）", "2,000", "3,600", "5,500", "8,000", "60%"],
        ["300户以上", "3,000", "5,000", "8,000", "12,000", "85%"],
        ["本月预计补贴（元）", {"runs": [{"text": "1,200", "color": "#E60012", "bold": True}]}, {"runs": [{"text": "2,200", "color": "#E60012", "bold": True}]}, {"runs": [{"text": "3,500", "color": "#E60012", "bold": True}]}, {"runs": [{"text": "5,000", "color": "#E60012", "bold": True}]}, "—"],
    ]
    right = _light_table(h, slide, "monthly-subsidy-table", 0.505, 0.515, 0.48, 0.285, subsidy_rows,
                         widths=[0.13, 0.07, 0.07, 0.07, 0.08, 0.13], heights=[0.042] + [0.04] * 6,
                         header_fill="#073E78", header_size=7.6, body_size=7.4, rich=True)
    right["cell_styles"]["6"] = {"fill": "#FFF0F2", "color": "#E60012", "bold": True, "size": 8.2, "align": "center", "valign": "mid"}
    for col in range(1, 5):
        right["cell_styles"][f"6,{col}"] = {"fill": "#FFF0F2", "color": "#E60012", "bold": True, "size": 9.0, "align": "center", "valign": "mid"}

    slide["texts"].extend([
        h.text("policy-note", "备注：服务费标准为含税标准；减收不罚；具体政策以省公司最新文件为准。", 0.025, 0.835, 0.45, 0.03, size=6.8, color="#28364A"),
        h.text("subsidy-note", "备注：按月度累计竣工户数达成对应档位，补贴与佣金可叠加享受。", 0.515, 0.815, 0.46, 0.03, size=6.8, color="#28364A"),
    ])
    return deck


REFERENCE_BUILDERS = {
    "native-table-merge-richtext-01": fttr_policy_layout,
}


def build_reference_layout(case, run_dir, optimized, helpers):
    builder = REFERENCE_BUILDERS.get(case.get("case_id"))
    if builder is None:
        return None
    return builder(case, run_dir, optimized, helpers)
