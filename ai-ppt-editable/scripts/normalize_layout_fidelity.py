#!/usr/bin/env python3
"""Normalize raster asset placement using alpha geometry and optional reference visual locks.

Two placement contracts are supported:

1. ``alpha-centroid-fit`` / ``align_by_alpha``: fit the visible alpha subject into
   the declared x/y/w/h slot, centering by the alpha-weighted centroid.
2. ``reference_visual_bbox_px``: fit the visible alpha subject to the source
   visual bounding box captured by PageGraph/Visual Lock. This is preferred for
   high-fidelity replay because transparent canvas padding no longer changes the
   visible subject's size or position.

``reference_visual_centroid_px`` may be supplied together with the reference bbox
when the source lock has a more precise visual centroid than the bbox center.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def _canvas(deck: dict) -> tuple[float, float]:
    return (
        float(deck.get("ref_width") or deck.get("reference_width") or deck.get("slide_width_px") or 1672),
        float(deck.get("ref_height") or deck.get("reference_height") or deck.get("slide_height_px") or 941),
    )


def _to_px(deck: dict, value: float, axis: int) -> float:
    if deck.get("units", "fraction") == "px":
        return float(value)
    return float(value) * _canvas(deck)[axis]


def _from_px(deck: dict, value: float, axis: int) -> float:
    if deck.get("units", "fraction") == "px":
        return float(value)
    return float(value) / _canvas(deck)[axis]


def _asset_path(layout: Path, deck: dict, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    assets = Path(deck.get("assets_dir") or layout.parent)
    if not assets.is_absolute():
        assets = (layout.parent / assets).resolve()
    return (assets / path).resolve()


def _alpha_geometry(path: Path) -> dict:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
    alpha = np.asarray(rgba.getchannel("A"), dtype=np.float64)
    ys, xs = np.where(alpha > 0)
    if not len(xs):
        raise ValueError(f"empty alpha asset: {path}")
    total = alpha.sum()
    gy, gx = np.indices(alpha.shape)
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)
    return {
        "canvas_w": rgba.width,
        "canvas_h": rgba.height,
        "visible_x": x0,
        "visible_y": y0,
        "visible_w": x1 - x0,
        "visible_h": y1 - y0,
        "centroid_x": float((gx * alpha).sum() / total),
        "centroid_y": float((gy * alpha).sum() / total),
    }


def _bbox_px(deck: dict, raw: object) -> tuple[float, float, float, float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    x, y, w, h = [float(value) for value in raw[:4]]
    if deck.get("units", "fraction") == "fraction" and max(abs(x), abs(y), abs(w), abs(h)) <= 1.5:
        return (_to_px(deck, x, 0), _to_px(deck, y, 1), _to_px(deck, w, 0), _to_px(deck, h, 1))
    return x, y, w, h


def _point_px(deck: dict, raw: object) -> tuple[float, float] | None:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    x, y = float(raw[0]), float(raw[1])
    if deck.get("units", "fraction") == "fraction" and max(abs(x), abs(y)) <= 1.5:
        return _to_px(deck, x, 0), _to_px(deck, y, 1)
    return x, y


def _placed_visible_bbox(geometry: dict, placed_x: float, placed_y: float, scale: float) -> list[float]:
    return [
        placed_x + geometry["visible_x"] * scale,
        placed_y + geometry["visible_y"] * scale,
        geometry["visible_w"] * scale,
        geometry["visible_h"] * scale,
    ]


def _place_to_reference_lock(deck: dict, icon: dict, geometry: dict) -> tuple[list[float], list[float], float, str]:
    reference = _bbox_px(deck, icon.get("reference_visual_bbox_px") or icon.get("source_visual_bbox_px"))
    if reference is None:
        raise ValueError("reference visual bbox is missing")
    rx, ry, rw, rh = reference
    if rw <= 0 or rh <= 0:
        raise ValueError(f"invalid reference visual bbox: {reference}")
    visual_scale = float(icon.get("visual_scale") or 1.0)
    if not 0 < visual_scale <= 1.5:
        raise ValueError(f"invalid visual_scale: {visual_scale}")
    fit_scale = min(rw / geometry["visible_w"], rh / geometry["visible_h"]) * visual_scale
    reference_centroid = _point_px(deck, icon.get("reference_visual_centroid_px") or icon.get("source_visual_centroid_px"))
    if reference_centroid is None:
        target_cx, target_cy = rx + rw / 2, ry + rh / 2
        source_cx = geometry["visible_x"] + geometry["visible_w"] / 2
        source_cy = geometry["visible_y"] + geometry["visible_h"] / 2
        alignment = "reference_bbox_center"
    else:
        target_cx, target_cy = reference_centroid
        source_cx = geometry["centroid_x"]
        source_cy = geometry["centroid_y"]
        alignment = "reference_visual_centroid"
    placed_x = target_cx - source_cx * fit_scale
    placed_y = target_cy - source_cy * fit_scale
    canvas_w = geometry["canvas_w"] * fit_scale
    canvas_h = geometry["canvas_h"] * fit_scale
    visible = _placed_visible_bbox(geometry, placed_x, placed_y, fit_scale)
    return [placed_x, placed_y, canvas_w, canvas_h], visible, fit_scale, alignment


def _place_to_slot(deck: dict, icon: dict, geometry: dict) -> tuple[list[float], list[float], float, str, list[float]]:
    x = _to_px(deck, icon.get("x", icon.get("left")), 0)
    y = _to_px(deck, icon.get("y", icon.get("top")), 1)
    w = _to_px(deck, icon.get("w", icon.get("width")), 0)
    h = _to_px(deck, icon.get("h", icon.get("height")), 1)
    visual_scale = float(icon.get("visual_scale") or 1.0)
    if not 0 < visual_scale <= 1.5:
        raise ValueError(f"invalid visual_scale: {visual_scale}")
    target_w, target_h = w * visual_scale, h * visual_scale
    target_x = x + (w - target_w) / 2
    target_y = y + (h - target_h) / 2
    scale = min(target_w / geometry["visible_w"], target_h / geometry["visible_h"])
    canvas_w = geometry["canvas_w"] * scale
    canvas_h = geometry["canvas_h"] * scale
    placed_x = target_x + target_w / 2 - geometry["centroid_x"] * scale
    placed_y = target_y + target_h / 2 - geometry["centroid_y"] * scale
    visible = _placed_visible_bbox(geometry, placed_x, placed_y, scale)
    return [placed_x, placed_y, canvas_w, canvas_h], visible, scale, "slot_alpha_centroid", [x, y, w, h]


def normalize(layout: Path) -> tuple[dict, list[dict]]:
    deck = json.loads(layout.read_text(encoding="utf-8"))
    records = []
    for slide_no, slide in enumerate(deck.get("slides") or [], 1):
        for index, icon in enumerate(slide.get("icons") or [], 1):
            reference_lock = icon.get("reference_visual_bbox_px") or icon.get("source_visual_bbox_px")
            if icon.get("placement_mode") != "alpha-centroid-fit" and icon.get("align_by_alpha") is not True and not reference_lock:
                continue
            source = icon.get("file") or icon.get("path") or icon.get("source_path")
            if not source:
                raise ValueError(f"slide {slide_no} icon {index} missing file")
            path = _asset_path(layout, deck, str(source))
            geometry = _alpha_geometry(path)
            object_id = icon.get("object_id") or icon.get("name") or f"icon-{index}"
            if reference_lock:
                placed, visible, scale, alignment = _place_to_reference_lock(deck, icon, geometry)
                target_slot = _bbox_px(deck, reference_lock)
                mode = "reference_visual_lock"
            else:
                placed, visible, scale, alignment, target_slot = _place_to_slot(deck, icon, geometry)
                mode = "alpha_centroid_slot"
            placed_x, placed_y, canvas_w, canvas_h = placed
            if deck.get("strict_input") and icon.get("allow_bleed") is not True:
                canvas_w_px, canvas_h_px = _canvas(deck)
                if placed_x < 0 or placed_y < 0 or placed_x + canvas_w > canvas_w_px or placed_y + canvas_h > canvas_h_px:
                    raise ValueError(f"alpha-centroid canvas escapes slide for {object_id}; use contain placement or allow_bleed for edge decorations")
            icon["x"] = _from_px(deck, placed_x, 0)
            icon["y"] = _from_px(deck, placed_y, 1)
            icon["w"] = _from_px(deck, canvas_w, 0)
            icon["h"] = _from_px(deck, canvas_h, 1)
            icon["placement_mode"] = "contain"
            icon["alpha_centroid_applied"] = True
            icon["visual_lock_applied"] = bool(reference_lock)
            records.append({
                "slide": slide_no,
                "object_id": object_id,
                "asset": str(path),
                "mode": mode,
                "alignment": alignment,
                "visual_scale": float(icon.get("visual_scale") or 1.0),
                "target_visual_bbox_px": [round(v, 3) for v in target_slot] if target_slot else None,
                "placed_visible_bbox_px": [round(v, 3) for v in visible],
                "placed_canvas_px": [round(v, 3) for v in placed],
                "scale": round(scale, 6),
                "alpha_geometry": geometry,
            })
    return deck, records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        deck, records = normalize(args.layout.resolve())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = {
            "schema": "ai-ppt-plus/alpha-centroid-layout/v2",
            "valid": True,
            "input": str(args.layout.resolve()),
            "output": str(args.output.resolve()),
            "normalized_count": len(records),
            "visual_lock_count": sum(1 for record in records if record["mode"] == "reference_visual_lock"),
            "records": records,
        }
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"schema": report["schema"], "valid": True, "normalized_count": len(records), "visual_lock_count": report["visual_lock_count"]}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"schema": "ai-ppt-plus/alpha-centroid-layout/v2", "valid": False, "status": "blocked", "code": "alpha_centroid_layout_failed", "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
