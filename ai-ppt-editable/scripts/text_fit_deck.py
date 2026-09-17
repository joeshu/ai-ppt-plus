#!/usr/bin/env python3
"""Run real-font text-fit preflight across every visible text slot in a deck layout."""
from __future__ import annotations

import argparse
import json
from argparse import Namespace
from pathlib import Path

from ppt_text_fit import best_fit


def _text(spec: object) -> str:
    if isinstance(spec, str):
        return spec
    if not isinstance(spec, dict):
        return "" if spec is None else str(spec)
    if spec.get("text") is not None:
        return str(spec.get("text"))
    if isinstance(spec.get("runs"), list):
        return "".join(_text(run) for run in spec["runs"])
    if isinstance(spec.get("paragraphs"), list):
        return "\n".join(_text(paragraph) for paragraph in spec["paragraphs"])
    if spec.get("run") is not None:
        return str(spec.get("run"))
    return ""


def _target_pt(spec: dict, default: float = 18.0) -> float:
    candidates = [spec.get("font_size_pt"), spec.get("size_pt"), spec.get("size")]
    run_sizes = []
    for run in spec.get("runs") or []:
        if isinstance(run, dict):
            for key in ("font_size_pt", "size_pt", "size", "font_size"):
                if run.get(key) is not None:
                    try:
                        run_sizes.append(float(run[key]))
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


def _slots(deck: dict):
    for slide_no, slide in enumerate(deck.get("slides") or [], 1):
        for index, spec in enumerate(slide.get("texts") or []):
            if _text(spec).strip():
                yield slide_no, f"text:{spec.get('object_id') or spec.get('name') or index+1}", spec, _box_px(deck, spec)
        for index, spec in enumerate(slide.get("shapes") or []):
            if _text(spec).strip():
                yield slide_no, f"shape:{spec.get('object_id') or spec.get('name') or index+1}", spec, _box_px(deck, spec)
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
                    yield slide_no, f"table:{table.get('object_id') or table_index+1}:{row_index},{col_index}", style, (col_w, row_h)
        for chart_index, chart in enumerate(slide.get("charts") or []):
            title = chart.get("title")
            if title:
                spec = {"text": str(title), "font_size_pt": chart.get("title_font_size_pt", 16), "font": chart.get("font") or deck.get("font_family")}
                chart_w, chart_h = _box_px(deck, chart)
                yield slide_no, f"chart:{chart.get('object_id') or chart_index+1}:title", spec, (chart_w, max(24.0, chart_h * 0.15))


def _make_args(deck: dict, spec: dict, text: str, box: tuple[float, float], font_file: str | None) -> Namespace:
    target = _target_pt(spec)
    slide_w = float(deck.get("ref_width") or deck.get("reference_width") or deck.get("slide_width_px") or 1672)
    slide_h = float(deck.get("ref_height") or deck.get("reference_height") or deck.get("slide_height_px") or 941)
    slide_in_w = float(deck.get("slide_width_in") or 13.333333)
    slide_in_h = float(deck.get("slide_height_in") or slide_in_w * slide_h / slide_w)
    return Namespace(text=text, box=f"{max(1.0, box[0])}x{max(1.0, box[1])}", font=str(spec.get("font") or spec.get("font_family") or deck.get("font_family") or "Noto Sans CJK SC"), font_file=font_file, bold=bool(spec.get("bold")), min_pt=max(4.0, min(8.0, target)), max_pt=max(target, 8.0), max_lines=int(spec.get("max_lines") or 0), line_spacing=float(spec.get("line_spacing") or 1.06), width_safety=float(spec.get("width_safety") or 0.92), height_safety=float(spec.get("height_safety") or 0.95), render_fudge=float(spec.get("render_fudge") or 1.01), target_pt=target, slide_px=f"{slide_w}x{slide_h}", slide_in=f"{slide_in_w}x{slide_in_h}")


def audit_layout(layout: Path, *, font_file: str | None = None) -> dict:
    deck = json.loads(layout.read_text(encoding="utf-8"))
    slots = []
    for slide_no, object_id, spec, box in _slots(deck):
        text = _text(spec)
        result = best_fit(_make_args(deck, spec, text, box, font_file))
        target = result.get("target") or {}
        slots.append({"slide": slide_no, "object_id": object_id, "text": text, "box_px": [round(box[0], 2), round(box[1], 2)], "target_pt": _target_pt(spec), "target_fits": bool(target.get("fits")), "recommended_pt": result.get("recommended_pt"), "reference_scale": result.get("reference_scale"), "line_count": target.get("line_count", result.get("line_count")), "font_path": result.get("font_path")})
    not_fit = [slot for slot in slots if not slot["target_fits"]]
    return {"schema": "ai-ppt-plus/text-fit-deck/v1", "valid": True, "layout": str(layout), "slot_count": len(slots), "fit_count": len(slots) - len(not_fit), "target_not_fit_count": len(not_fit), "all_slots_measured": True, "slots": slots}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", type=Path)
    parser.add_argument("--font-file")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--fail-on-target-not-fit", action="store_true")
    args = parser.parse_args()
    try:
        report = audit_layout(args.layout.resolve(), font_file=args.font_file)
    except Exception as exc:
        print(json.dumps({"schema": "ai-ppt-plus/text-fit-deck/v1", "valid": False, "status": "blocked", "code": "text_fit_deck_failed", "message": str(exc)}, ensure_ascii=False))
        return 2
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("schema", "valid", "slot_count", "fit_count", "target_not_fit_count")}, ensure_ascii=False))
    return 3 if args.fail_on_target_not_fit and report["target_not_fit_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
