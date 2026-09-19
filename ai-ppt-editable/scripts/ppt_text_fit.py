#!/usr/bin/env python3
"""Preflight editable PowerPoint text with real runtime font metrics.

The fitter preserves reference line topology when supplied. It uses the same
runtime-resolved font family that authoring should use and reports geometry
shortfalls instead of silently shrinking typography to compensate for a wrong
text slot.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from runtime_fonts import resolve_font_file


def _pair(value: str, separator: str = "x") -> tuple[float, float]:
    left, right = value.lower().split(separator, 1)
    return float(left), float(right)


def find_font(font_name: str, bold: bool, explicit: str | None = None) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if path.is_file():
            return path
        raise FileNotFoundError(f"font file not found: {path}")
    resolved = resolve_font_file(font_name, bold=bold)
    if resolved and resolved.is_file():
        return resolved
    raise FileNotFoundError(
        f"no usable runtime font file found for {font_name!r}; "
        "prepare/resolve the CJK runtime font before text fitting"
    )


def _width(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, text: str) -> float:
    if not text:
        return 0.0
    box = draw.textbbox((0, 0), text, font=font)
    return float(max(0, box[2] - box[0]))


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_./:+#-]+|\s+|.", text, flags=re.DOTALL)


def wrap(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, text: str, max_width: float) -> list[str]:
    lines: list[str] = []
    current = ""
    for token in _tokens(text):
        candidate = current + token
        if current and _width(draw, font, candidate) > max_width:
            lines.append(current.rstrip())
            current = token.lstrip()
            if _width(draw, font, current) > max_width and len(current) > 1:
                fragment = ""
                for char in current:
                    if fragment and _width(draw, font, fragment + char) > max_width:
                        lines.append(fragment)
                        fragment = char
                    else:
                        fragment += char
                current = fragment
        else:
            current = candidate
    lines.append(current.rstrip())
    return [line for line in lines if line] or [""]


def measure(text: str, pt: float, font_path: Path, px_per_pt: float, width_px: float,
            line_spacing: float, width_safety: float, render_fudge: float) -> dict:
    font_px = max(1, int(round(pt * px_per_pt * render_fudge)))
    font = ImageFont.truetype(str(font_path), font_px)
    draw = ImageDraw.Draw(Image.new("RGB", (max(4, int(width_px * 2)), 4096), "white"))
    lines: list[str] = []
    for paragraph in text.split("\n"):
        lines.extend(wrap(draw, font, paragraph, width_px * width_safety))
    boxes = [draw.textbbox((0, 0), line or "口", font=font) for line in lines]
    widths = [max(0, box[2] - box[0]) for box in boxes]
    glyph_heights = [max(0, box[3] - box[1]) for box in boxes]
    line_height = max(max(glyph_heights, default=0), font_px * 0.82) * line_spacing
    occupied = sum(widths) * max(max(glyph_heights, default=0), 1)
    return {
        "pt": pt,
        "font_px": font_px,
        "lines": lines,
        "line_count": len(lines),
        "width_px": max(widths, default=0),
        "height_px": line_height * len(lines),
        "line_height_px": line_height,
        "occupied_glyph_proxy_px2": occupied,
    }


def best_fit(args: argparse.Namespace) -> dict:
    box_w, box_h = _pair(args.box)
    slide_w_px, _ = _pair(args.slide_px)
    slide_w_in, _ = _pair(args.slide_in)
    px_per_pt = (slide_w_px / slide_w_in) / 72.0
    font_path = find_font(args.font, args.bold, args.font_file)

    def geometry_fits(row: dict) -> bool:
        return (
            row["width_px"] <= box_w * args.width_safety
            and row["height_px"] <= box_h * args.height_safety
            and (args.max_lines <= 0 or row["line_count"] <= args.max_lines)
        )

    def topology_matches(row: dict) -> bool:
        return args.target_lines <= 0 or row["line_count"] == args.target_lines

    def full_fit(row: dict) -> bool:
        return geometry_fits(row) and topology_matches(row)

    # Exact line topology is not monotonic under the old binary-search predicate:
    # when the candidate has too few lines we often need a larger font/narrower
    # slot, not a smaller font. Scan from largest to smallest when topology is
    # known, then fall back to the closest topology for diagnosis.
    if args.target_lines > 0:
        step = max(0.10, args.scan_step)
        count = max(1, int(math.ceil((args.max_pt - args.min_pt) / step)))
        candidates = []
        for index in range(count + 1):
            point = max(args.min_pt, args.max_pt - index * step)
            row = measure(args.text, point, font_path, px_per_pt, box_w,
                          args.line_spacing, args.width_safety, args.render_fudge)
            candidates.append(row)
        exact = [row for row in candidates if full_fit(row)]
        if exact:
            best = exact[0]
        else:
            geometrically_valid = [row for row in candidates if geometry_fits(row)] or candidates
            best = min(
                geometrically_valid,
                key=lambda row: (abs(row["line_count"] - args.target_lines), -row["pt"]),
            )
    else:
        low, high, best = args.min_pt, args.max_pt, None
        for _ in range(18):
            point = (low + high) / 2.0
            row = measure(args.text, point, font_path, px_per_pt, box_w,
                          args.line_spacing, args.width_safety, args.render_fudge)
            if geometry_fits(row):
                best, low = row, point
            else:
                high = point
        if best is None:
            best = measure(args.text, args.min_pt, font_path, px_per_pt, box_w,
                           args.line_spacing, args.width_safety, args.render_fudge)

    best.update({
        "recommended_pt": round(best["pt"], 2),
        "font_path": str(font_path),
        "px_per_pt": px_per_pt,
        "box_px": [box_w, box_h],
        "fits": full_fit(best),
        "geometry_fits": geometry_fits(best),
        "line_topology_preserved": topology_matches(best),
        "line_count_delta": (best["line_count"] - args.target_lines) if args.target_lines > 0 else 0,
        "utilization": {
            "width": round(best["width_px"] / box_w, 4) if box_w else 0.0,
            "height": round(best["height_px"] / box_h, 4) if box_h else 0.0,
        },
    })
    if args.target_pt is not None:
        target = measure(args.text, args.target_pt, font_path, px_per_pt, box_w,
                         args.line_spacing, args.width_safety, args.render_fudge)
        target["fits"] = full_fit(target)
        target["geometry_fits"] = geometry_fits(target)
        target["line_topology_preserved"] = topology_matches(target)
        target["required_box_px"] = [
            math.ceil(target["width_px"] / args.width_safety),
            math.ceil(target["height_px"] / args.height_safety),
        ]
        target["box_deficit_px"] = [
            max(0, target["required_box_px"][0] - box_w),
            max(0, target["required_box_px"][1] - box_h),
        ]
        best["target"] = target
        best["reference_scale"] = round(best["recommended_pt"] / args.target_pt, 4) if args.target_pt else 1.0
    best["settings"] = {
        "font": args.font,
        "bold": args.bold,
        "max_lines": args.max_lines,
        "target_lines": args.target_lines,
        "line_spacing": args.line_spacing,
        "width_safety": args.width_safety,
        "height_safety": args.height_safety,
        "render_fudge": args.render_fudge,
        "scan_step": args.scan_step,
        "runtime_font_required": True,
    }
    return best


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    argv = sys.argv[1:]
    if "--text" in argv:
        index = argv.index("--text")
        if index + 1 < len(argv):
            argv[index] = f"--text={argv[index + 1]}"
            del argv[index + 1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", required=True)
    parser.add_argument("--box", required=True, help="exported pixel box, e.g. 980x42")
    parser.add_argument("--font", default="Noto Sans CJK SC")
    parser.add_argument("--font-file")
    parser.add_argument("--bold", action="store_true")
    parser.add_argument("--min-pt", type=float, default=8)
    parser.add_argument("--max-pt", type=float, default=36)
    parser.add_argument("--max-lines", type=int, default=0)
    parser.add_argument("--target-lines", type=int, default=0, help="exact observable reference line count; 0 disables exact topology matching")
    parser.add_argument("--scan-step", type=float, default=0.25, help="point-size scan step when --target-lines is used")
    parser.add_argument("--line-spacing", type=float, default=1.06)
    parser.add_argument("--width-safety", type=float, default=0.92)
    parser.add_argument("--height-safety", type=float, default=0.95)
    parser.add_argument("--render-fudge", type=float, default=1.01)
    parser.add_argument("--target-pt", type=float)
    parser.add_argument("--slide-px", default="1672x941")
    parser.add_argument("--slide-in", default="13.333333x7.505")
    args = parser.parse_args(argv)
    print(json.dumps(best_fit(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
