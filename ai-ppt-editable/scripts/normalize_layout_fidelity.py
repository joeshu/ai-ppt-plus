#!/usr/bin/env python3
"""Normalize image layout geometry using alpha-weighted visual centroids.

Only icons that explicitly declare ``placement_mode: alpha-centroid-fit`` (or
``align_by_alpha: true``) are changed. The authoring backend can then consume
the resulting ordinary x/y/w/h box without needing raster-specific logic.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def _canvas(deck: dict) -> tuple[float, float]:
    return (float(deck.get("ref_width") or deck.get("reference_width") or deck.get("slide_width_px") or 1672), float(deck.get("ref_height") or deck.get("reference_height") or deck.get("slide_height_px") or 941))


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
    return {"canvas_w": rgba.width, "canvas_h": rgba.height, "visible_w": int(xs.max() - xs.min() + 1), "visible_h": int(ys.max() - ys.min() + 1), "centroid_x": float((gx * alpha).sum() / total), "centroid_y": float((gy * alpha).sum() / total)}


def normalize(layout: Path) -> tuple[dict, list[dict]]:
    deck = json.loads(layout.read_text(encoding="utf-8"))
    records = []
    for slide_no, slide in enumerate(deck.get("slides") or [], 1):
        for index, icon in enumerate(slide.get("icons") or [], 1):
            if icon.get("placement_mode") != "alpha-centroid-fit" and icon.get("align_by_alpha") is not True:
                continue
            source = icon.get("file") or icon.get("path") or icon.get("source_path")
            if not source:
                raise ValueError(f"slide {slide_no} icon {index} missing file")
            path = _asset_path(layout, deck, str(source))
            geometry = _alpha_geometry(path)
            x = _to_px(deck, icon.get("x", icon.get("left")), 0)
            y = _to_px(deck, icon.get("y", icon.get("top")), 1)
            w = _to_px(deck, icon.get("w", icon.get("width")), 0)
            h = _to_px(deck, icon.get("h", icon.get("height")), 1)
            visual_scale = float(icon.get("visual_scale") or 1.0)
            if not 0 < visual_scale <= 1.5:
                raise ValueError(f"invalid visual_scale for {icon.get('object_id') or index}: {visual_scale}")
            target_w, target_h = w * visual_scale, h * visual_scale
            target_x = x + (w - target_w) / 2
            target_y = y + (h - target_h) / 2
            scale = min(target_w / geometry["visible_w"], target_h / geometry["visible_h"])
            canvas_w = geometry["canvas_w"] * scale
            canvas_h = geometry["canvas_h"] * scale
            placed_x = target_x + target_w / 2 - geometry["centroid_x"] * scale
            placed_y = target_y + target_h / 2 - geometry["centroid_y"] * scale
            if deck.get("strict_input") and icon.get("allow_bleed") is not True:
                canvas_w_px, canvas_h_px = _canvas(deck)
                if placed_x < 0 or placed_y < 0 or placed_x + canvas_w > canvas_w_px or placed_y + canvas_h > canvas_h_px:
                    raise ValueError(f"alpha-centroid canvas escapes slide for {icon.get('object_id') or index}; use contain placement or allow_bleed for edge decorations")
            original = [x, y, w, h]
            placed = [placed_x, placed_y, canvas_w, canvas_h]
            icon["x"] = _from_px(deck, placed_x, 0)
            icon["y"] = _from_px(deck, placed_y, 1)
            icon["w"] = _from_px(deck, canvas_w, 0)
            icon["h"] = _from_px(deck, canvas_h, 1)
            icon["placement_mode"] = "contain"
            icon["alpha_centroid_applied"] = True
            records.append({"slide": slide_no, "object_id": icon.get("object_id") or icon.get("name") or f"icon-{index}", "asset": str(path), "visual_scale": visual_scale, "target_slot_px": [round(v, 3) for v in original], "placed_canvas_px": [round(v, 3) for v in placed], "alpha_geometry": geometry})
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
        report = {"schema": "ai-ppt-plus/alpha-centroid-layout/v1", "valid": True, "input": str(args.layout.resolve()), "output": str(args.output.resolve()), "normalized_count": len(records), "records": records}
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"schema": report["schema"], "valid": True, "normalized_count": len(records)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"schema": "ai-ppt-plus/alpha-centroid-layout/v1", "valid": False, "status": "blocked", "code": "alpha_centroid_layout_failed", "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
