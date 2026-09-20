#!/usr/bin/env python3
"""Run real-font text-fit preflight across every visible text slot in a deck layout."""
from __future__ import annotations

import argparse
import json
import re
from argparse import Namespace
from pathlib import Path

from ppt_text_fit import best_fit
from text_model import measurement_scope, number_unit_trace, text_content, text_trace


TEXT_SLOT_KINDS = (
    "text",
    "shape_text",
    "table_cell",
    "chart_title",
    "chart_legend",
    "chart_category_label",
    "chart_data_label",
)


def _text(spec: object) -> str:
    return text_content(spec)


def _style_value(spec: dict, key: str):
    value = spec.get(key)
    if value is not None:
        return value
    style = spec.get("style")
    if isinstance(style, dict):
        return style.get(key)
    return None


def _target_pt(spec: dict, default: float = 18.0) -> float:
    candidates = [_style_value(spec, key) for key in ("font_size_pt", "size_pt", "size", "font_size")]
    run_sizes = []
    for run in spec.get("runs") or []:
        if isinstance(run, dict):
            for key in ("font_size_pt", "size_pt", "size", "font_size"):
                value = run.get(key)
                if value is None and isinstance(run.get("style"), dict):
                    value = run["style"].get(key)
                if value is not None:
                    try:
                        run_sizes.append(float(value))
                    except (TypeError, ValueError):
                        pass
                    break
    if run_sizes:
        candidates.insert(0, max(run_sizes))
    for value in candidates:
        if value is not None:
            try:
                number = float(value)
                if number > 0:
                    return number
            except (TypeError, ValueError):
                pass
    return default


PRODUCER_KINDS = {
    "text_box", "rich_text_runs", "table_cell", "badge_label", "chart_label", "number_unit", "other",
}


def _producer_kind(kind: str, spec: dict, trace: dict) -> str:
    explicit = spec.get("producer_kind") or spec.get("text_producer_kind")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if number_unit_trace(spec, content=trace["content"], fallback_id=trace["text_spec_id"]) is not None:
        return "number_unit"
    if kind == "text":
        return "rich_text_runs" if trace["run_count"] else "text_box"
    if kind == "shape_text":
        return "badge_label"
    if kind == "table_cell":
        return "table_cell"
    if kind.startswith("chart_"):
        return "chart_label"
    return "other"


def _target_lines(spec: dict, text: str) -> int:
    """Resolve an observable reference line count for the fitter.

    Explicit producer evidence wins.  Otherwise explicit line breaks are
    treated as topology evidence unless the producer deliberately opts into
    reflow.  ``max_lines`` remains a capacity constraint, not a reference
    topology declaration.
    """
    for key in ("target_lines", "reference_line_count"):
        value = spec.get(key)
        if value is not None:
            try:
                number = int(value)
            except (TypeError, ValueError):
                return 0
            return max(0, number)
    if spec.get("allow_reflow") is not True and re.search(r"\r\n?|\n", text):
        return max(1, len(re.split(r"\r\n?|\n", text)))
    return 0


def _box_px(deck: dict, spec: dict, *, fraction: tuple[float, float] | None = None) -> tuple[float, float]:
    ref_w = float(deck.get("ref_width") or deck.get("reference_width") or deck.get("slide_width_px") or 1672)
    ref_h = float(deck.get("ref_height") or deck.get("reference_height") or deck.get("slide_height_px") or 941)
    if fraction is not None:
        return fraction
    if isinstance(spec.get("bbox"), list) and len(spec["bbox"]) >= 4:
        w, h = float(spec["bbox"][2]), float(spec["bbox"][3])
    else:
        w, h = float(spec.get("w") or spec.get("width") or 0), float(spec.get("h") or spec.get("height") or 0)
    if deck.get("units", "fraction") == "fraction":
        w *= ref_w
        h *= ref_h
    return w, h


def _chart_text_spec(chart: dict, text: object, *, size: float, max_lines: int = 1) -> dict:
    return {
        "text": str(text),
        "font_size_pt": size,
        "font": chart.get("font"),
        "bold": False,
        "max_lines": max_lines,
        "width_safety": chart.get("text_fit_width_safety", 0.90),
        "height_safety": chart.get("text_fit_height_safety", 0.92),
    }


def _chart_slots(deck: dict, slide_no: int, chart_index: int, chart: dict):
    chart_id = chart.get("object_id") or chart.get("name") or chart_index + 1
    chart_w, chart_h = _box_px(deck, chart)
    title = chart.get("title")
    if title:
        spec = _chart_text_spec(chart, title, size=float(chart.get("title_font_size_pt", 16)), max_lines=2)
        yield slide_no, "chart_title", f"chart:{chart_id}:title", spec, (chart_w, max(24.0, chart_h * 0.15))

    series = [item for item in (chart.get("series") or []) if isinstance(item, dict)]
    legend_enabled = bool(chart.get("legend", len(series) > 1))
    if legend_enabled and series:
        legend_w = max(24.0, chart_w / max(1, len(series)))
        legend_h = max(18.0, chart_h * 0.10)
        legend_size = float(chart.get("legend_font_size_pt", chart.get("chart_legend_size", 8)))
        for series_index, item in enumerate(series):
            name = item.get("name")
            if name is None or not str(name).strip():
                continue
            spec = _chart_text_spec(chart, name, size=legend_size)
            yield slide_no, "chart_legend", f"chart:{chart_id}:legend:{series_index}", spec, (legend_w, legend_h)

    categories = list(chart.get("categories") or [])
    if categories:
        plot_w = chart_w * 0.82
        category_w = max(18.0, plot_w / max(1, len(categories)))
        category_h = max(18.0, chart_h * 0.11)
        category_size = float(chart.get("category_font_size_pt", chart.get("chart_tick_size", 8)))
        for category_index, category in enumerate(categories):
            if category is None or not str(category).strip():
                continue
            spec = _chart_text_spec(chart, category, size=category_size, max_lines=2)
            yield slide_no, "chart_category_label", f"chart:{chart_id}:category:{category_index}", spec, (category_w, category_h)

    if chart.get("data_labels") and series:
        point_count = max([len(item.get("values") or []) for item in series] + [len(categories), 1])
        label_w = max(24.0, chart_w * 0.82 / point_count * 0.95)
        label_h = max(16.0, chart_h * 0.09)
        label_size = float(chart.get("data_label_font_size_pt", chart.get("chart_label_size", 7)))
        for series_index, item in enumerate(series):
            for point_index, value in enumerate(item.get("values") or []):
                if value is None or value == "":
                    continue
                spec = _chart_text_spec(chart, value, size=label_size)
                yield slide_no, "chart_data_label", f"chart:{chart_id}:data:{series_index}:{point_index}", spec, (label_w, label_h)


def _slots(deck: dict):
    """Yield every formal text-producing path with a stable slot kind."""
    for slide_no, slide in enumerate(deck.get("slides") or [], 1):
        for index, spec in enumerate(slide.get("texts") or []):
            if _text(spec).strip():
                yield slide_no, "text", f"text:{spec.get('object_id') or spec.get('name') or index+1}", spec, _box_px(deck, spec)
        for index, spec in enumerate(slide.get("shapes") or []):
            if _text(spec).strip():
                yield slide_no, "shape_text", f"shape:{spec.get('object_id') or spec.get('name') or index+1}", spec, _box_px(deck, spec)
        for table_index, table in enumerate(slide.get("tables") or []):
            rows = table.get("rows") or []
            columns = int(table.get("columns") or max((len(row) for row in rows if isinstance(row, list)), default=1))
            table_w, table_h = _box_px(deck, table)
            row_h = table_h / max(1, len(rows))
            col_w = table_w / max(1, columns)
            for row_index, row in enumerate(rows):
                if not isinstance(row, list):
                    continue
                for col_index, cell in enumerate(row):
                    text = _text(cell)
                    if not text.strip():
                        continue
                    style = dict(table)
                    style.pop("rows", None)
                    if isinstance(cell, dict):
                        style.update(cell)
                    style["text"] = text
                    yield slide_no, "table_cell", f"table:{table.get('object_id') or table_index+1}:{row_index},{col_index}", style, (col_w, row_h)
        for chart_index, chart in enumerate(slide.get("charts") or []):
            yield from _chart_slots(deck, slide_no, chart_index, chart)


def _make_args(deck: dict, spec: dict, text: str, box: tuple[float, float], font_file: str | None) -> Namespace:
    target = _target_pt(spec)
    font = _style_value(spec, "font") or _style_value(spec, "font_family")
    bold = _style_value(spec, "bold")
    line_spacing = _style_value(spec, "line_spacing")
    slide_w = float(deck.get("ref_width") or deck.get("reference_width") or deck.get("slide_width_px") or 1672)
    slide_h = float(deck.get("ref_height") or deck.get("reference_height") or deck.get("slide_height_px") or 941)
    slide_in_w = float(deck.get("slide_width_in") or 13.333333)
    slide_in_h = float(deck.get("slide_height_in") or slide_in_w * slide_h / slide_w)
    return Namespace(
        text=text,
        box=f"{max(1.0, box[0])}x{max(1.0, box[1])}",
        font=str(font or deck.get("font_family") or "Noto Sans CJK SC"),
        font_file=font_file,
        bold=bool(bold),
        min_pt=max(4.0, min(8.0, target)),
        max_pt=max(target, 8.0),
        max_lines=int(spec.get("max_lines") or 0),
        target_lines=_target_lines(spec, text),
        line_spacing=float(line_spacing or 1.06),
        width_safety=float(spec.get("width_safety") or 0.92),
        height_safety=float(spec.get("height_safety") or 0.95),
        render_fudge=float(spec.get("render_fudge") or 1.01),
        target_pt=target,
        slide_px=f"{slide_w}x{slide_h}",
        slide_in=f"{slide_in_w}x{slide_in_h}",
    )


def audit_layout(layout: Path, *, font_file: str | None = None) -> dict:
    deck = json.loads(layout.read_text(encoding="utf-8"))
    slots = []
    coverage: dict[str, int] = {kind: 0 for kind in TEXT_SLOT_KINDS}
    trace_defects = []
    for slide_no, kind, object_id, spec, box in _slots(deck):
        coverage[kind] = coverage.get(kind, 0) + 1
        text = _text(spec)
        trace = text_trace(spec, fallback_id=object_id)
        scope = measurement_scope(spec, fallback_id=object_id)
        number_unit = number_unit_trace(spec, content=text, fallback_id=trace["text_spec_id"])
        producer_kind = _producer_kind(kind, spec, trace)
        slot_trace_defects = []
        if trace["content_matches_runs"] is False:
            slot_trace_defects.append("content_runs_mismatch")
        if scope["kind"] not in {"whole_phrase", "sub_box"}:
            slot_trace_defects.append("measurement_scope_invalid")
        if producer_kind not in PRODUCER_KINDS:
            slot_trace_defects.append("producer_kind_invalid")
        if number_unit is not None and number_unit["combined_text"] != text:
            slot_trace_defects.append("number_unit_content_mismatch")
        if slot_trace_defects:
            trace_defects.append({"object_id": object_id, "codes": slot_trace_defects})
        result = best_fit(_make_args(deck, spec, text, box, font_file))
        target = result.get("target") or {}
        reference_scale = result.get("reference_scale")
        target_fits = bool(target.get("fits", result.get("fits")))
        geometry_fits = bool(target.get("geometry_fits", result.get("geometry_fits")))
        topology_preserved = bool(target.get("line_topology_preserved", result.get("line_topology_preserved", True)))
        # Reference scale is evidence for review, not a universal numeric
        # release gate.  A slot is a geometry defect only when its measured
        # target geometry fails; topology is reported separately below.
        geometry_defect = not geometry_fits
        topology_defect = not topology_preserved
        required_box = target.get("required_box_px", result.get("required_box_px"))
        box_deficit = target.get("box_deficit_px", result.get("box_deficit_px"))
        slots.append({
            "slide": slide_no,
            "kind": kind,
            "object_id": object_id,
            "text": text,
            "text_spec_id": trace["text_spec_id"],
            "producer_kind": producer_kind,
            "measurement_scope": scope,
            "content_sha256": trace["content_sha256"],
            "content_matches_runs": trace["content_matches_runs"],
            "run_count": trace["run_count"],
            "run_ids": trace["run_ids"],
            "run_trace": trace["run_trace"],
            "run_style_sha256": trace["run_style_sha256"],
            "base_style_sha256": trace["base_style_sha256"],
            "number_unit": number_unit,
            "trace_defects": slot_trace_defects,
            "box_px": [round(box[0], 2), round(box[1], 2)],
            "target_pt": _target_pt(spec),
            "target_lines": result.get("target_lines", 0),
            "target_fits": target_fits,
            "geometry_fits": geometry_fits,
            "line_topology_preserved": topology_preserved,
            "topology_defect": topology_defect,
            "recommended_pt": result.get("recommended_pt"),
            "reference_scale": reference_scale,
            "required_box_px": required_box,
            "box_deficit_px": box_deficit,
            "geometry_defect": geometry_defect,
            "repair_hint": result.get("repair_hint"),
            "repair_priority": "geometry_first" if geometry_defect else ("line-topology" if topology_defect else "none"),
            "line_count": target.get("line_count", result.get("line_count")),
            "recommended_line_count": result.get("line_count"),
            "font_path": result.get("font_path"),
        })
    not_fit = [slot for slot in slots if not slot["target_fits"]]
    geometry_defects = [slot for slot in slots if slot["geometry_defect"]]
    topology_defects = [slot for slot in slots if slot["topology_defect"]]
    measured_ids = [slot["object_id"] for slot in slots]
    duplicate_ids = sorted({item for item in measured_ids if measured_ids.count(item) > 1})
    return {
        "schema": "ai-ppt-plus/text-fit-deck/v3",
        "valid": not duplicate_ids and not trace_defects,
        "layout": str(layout),
        "slot_count": len(slots),
        "fit_count": len(slots) - len(not_fit),
        "target_not_fit_count": len(not_fit),
        "geometry_defect_count": len(geometry_defects),
        "topology_defect_count": len(topology_defects),
        "all_slots_measured": True,
        "coverage_by_kind": coverage,
        "measured_object_ids": measured_ids,
        "duplicate_object_ids": duplicate_ids,
        "trace_defect_count": len(trace_defects),
        "trace_defects": trace_defects,
        "repair_policy": "geometry_first_font_shrink_last",
        "text_fit_schema": "ai-ppt-plus/text-fit/v2",
        "slots": slots,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", type=Path)
    parser.add_argument("--font-file")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--fail-on-target-not-fit", action="store_true")
    parser.add_argument("--require-kind", action="append", choices=list(TEXT_SLOT_KINDS), default=[])
    args = parser.parse_args()
    try:
        report = audit_layout(args.layout.resolve(), font_file=args.font_file)
    except Exception as exc:
        print(json.dumps({"schema": "ai-ppt-plus/text-fit-deck/v3", "valid": False, "status": "blocked", "code": "text_fit_deck_failed", "message": str(exc)}, ensure_ascii=False))
        return 2
    missing_kinds = [kind for kind in args.require_kind if report["coverage_by_kind"].get(kind, 0) == 0]
    report["required_kinds"] = args.require_kind
    report["missing_required_kinds"] = missing_kinds
    if missing_kinds:
        report["valid"] = False
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("schema", "valid", "slot_count", "fit_count", "target_not_fit_count", "geometry_defect_count", "coverage_by_kind", "missing_required_kinds")}, ensure_ascii=False))
    if not report["valid"]:
        return 4
    return 3 if args.fail_on_target_not_fit and report["target_not_fit_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
