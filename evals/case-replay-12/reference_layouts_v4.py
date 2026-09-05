"""Fourth-pass residual convergence for the FTTR frozen-reference replay."""
from __future__ import annotations

from reference_layouts_v3 import fttr_policy_layout_v3


def _by_id(items, object_id):
    return next((item for item in items if item.get("object_id") == object_id), None)


def fttr_policy_layout_v4(case, run_dir, optimized, h):
    deck = fttr_policy_layout_v3(case, run_dir, optimized, h)
    slide = deck["slides"][0]
    texts = slide.get("texts", []) or []
    groups = slide.get("groups", []) or []
    shapes = slide.get("shapes", []) or []
    tables = slide.get("tables", []) or []

    # Header in the frozen reference occupies more horizontal area than v3.
    fttr = _by_id(texts, "title-fttr")
    title = _by_id(texts, "title")
    brand = _by_id(texts, "brand-mark")
    if brand:
        brand.update({"x": 0.018, "w": 0.064, "size": 40})
    if fttr:
        fttr.update({"x": 0.083, "w": 0.125, "size": 37})
    if title:
        title.update({"x": 0.199, "w": 0.39, "size": 33.5})

    # The three card bottoms in v3 are still ~13 px too high at the 900 px
    # comparison render. Extend only their outer native groups; keep row anchors.
    for object_id in ("commission-new", "commission-stock", "commission-upgrade"):
        group = _by_id(groups, object_id)
        if group:
            group["h"] = 0.357

    # Increase line-icon mass to better match the reference's larger blue icons.
    for text in texts:
        object_id = str(text.get("object_id", ""))
        if "-icon-" in object_id:
            text["size"] = 25 if object_id.endswith("-icon-2") else 27
            text["w"] = 0.052
        elif object_id.endswith(("-依据", "-周期", "-结果", "-图标")):
            text["size"] = 11.5

    # Policy divider is ~16 px too high in v3; shift only the band and its copy.
    divider = _by_id(shapes, "policy-divider")
    if divider:
        divider["y"] = float(divider["y"]) + 0.0175
    for object_id in ("policy-divider-left", "policy-divider-text", "policy-divider-right"):
        item = _by_id(texts, object_id)
        if item:
            item["y"] = float(item["y"]) + 0.0175

    # Reference tables use visibly larger type. Raise typography without changing
    # the already-aligned v3 table geometry or merge topology.
    left = _by_id(tables, "policy-merged-table")
    right = _by_id(tables, "monthly-subsidy-table")
    if left:
        left["size"] = 8.7
        for key, style in (left.get("cell_styles") or {}).items():
            if not isinstance(style, dict):
                continue
            if str(key) == "0":
                style["size"] = 9.1
            elif "," not in str(key):
                style["size"] = max(float(style.get("size", 8.0)), 8.55)
    if right:
        right["size"] = 8.25
        for key, style in (right.get("cell_styles") or {}).items():
            if not isinstance(style, dict):
                continue
            if str(key) == "0":
                style["size"] = 8.0
            elif "," not in str(key):
                style["size"] = max(float(style.get("size", 7.6)), 8.05)

    # Add the blue rounded outer containers visible around table + note areas.
    # They are authored before tables, so the white fill becomes a substrate and
    # only the perimeter remains visible after the tables are placed above it.
    shapes.extend([
        h.shape("policy-table-outer-frame", "rounded_rect", 0.013, 0.568, 0.478, 0.371,
                fill="#FFFFFF", line="#0A3C76", line_width=1.05),
        h.shape("subsidy-table-outer-frame", "rounded_rect", 0.504, 0.568, 0.482, 0.371,
                fill="#FFFFFF", line="#0A3C76", line_width=1.05),
    ])
    return deck


REFERENCE_BUILDERS_V4 = {
    "native-table-merge-richtext-01": fttr_policy_layout_v4,
}


def build_reference_layout_v4(case, run_dir, optimized, helpers):
    builder = REFERENCE_BUILDERS_V4.get(case.get("case_id"))
    if builder is None:
        return None
    return builder(case, run_dir, optimized, helpers)
