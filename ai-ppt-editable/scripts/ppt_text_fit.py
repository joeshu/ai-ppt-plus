#!/usr/bin/env python3
"""Preflight editable PowerPoint text with real font metrics.

Adapted from knight-imagetopptx-skill's text-fit helper and made portable for
the bundled Noto Sans SC fonts used by ai-ppt-editable.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FONT_FILES = {
    "noto sans sc": ("NotoSansSC-Regular.ttf", "NotoSansSC-Bold.ttf"),
    "noto sans cjk sc": ("NotoSansSC-Regular.ttf", "NotoSansSC-Bold.ttf"),
    "思源黑体": ("NotoSansSC-Regular.ttf", "NotoSansSC-Bold.ttf"),
    "microsoft yahei": ("msyh.ttc", "msyhbd.ttc"),
    "微软雅黑": ("msyh.ttc", "msyhbd.ttc"),
    "arial": ("arial.ttf", "arialbd.ttf"),
}


def _pair(value: str, separator: str = "x") -> tuple[float, float]:
    left, right = value.lower().split(separator, 1)
    return float(left), float(right)


def find_font(font_name: str, bold: bool, explicit: str | None = None) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if path.is_file():
            return path
        raise FileNotFoundError(f"font file not found: {path}")
    regular, bold_file = FONT_FILES.get(
        font_name.strip().lower(),
        ("NotoSansSC-Regular.ttf", "NotoSansSC-Bold.ttf"),
    )
    filename = bold_file if bold else regular
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "assets" / "fonts" / filename,
        here.parents[2] / "assets" / "fonts" / filename,
        Path("C:/Windows/Fonts") / filename,
        Path("/usr/share/fonts/opentype/noto") / filename,
        Path("/usr/share/fonts/truetype/noto") / filename,
    ]
    # YaHei may be requested on non-Windows runners. Use the bundled licensed
    # Noto fallback only for measurement and report the resolved file.
    candidates.extend([
        here.parents[1] / "assets" / "fonts" / ("NotoSansSC-Bold.ttf" if bold else "NotoSansSC-Regular.ttf"),
        here.parents[2] / "assets" / "fonts" / ("NotoSansSC-Bold.ttf" if bold else "NotoSansSC-Regular.ttf"),
    ])
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(f"no usable font file found for {font_name!r}")


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
    return {
        "pt": pt,
        "font_px": font_px,
        "lines": lines,
        "line_count": len(lines),
        "width_px": max(widths, default=0),
        "height_px": line_height * len(lines),
        "line_height_px": line_height,
    }


def best_fit(args: argparse.Namespace) -> dict:
    box_w, box_h = _pair(args.box)
    slide_w_px, _ = _pair(args.slide_px)
    slide_w_in, _ = _pair(args.slide_in)
    px_per_pt = (slide_w_px / slide_w_in) / 72.0
    font_path = find_font(args.font, args.bold, args.font_file)

    def fits(row: dict) -> bool:
        return (
            row["width_px"] <= box_w * args.width_safety
            and row["height_px"] <= box_h * args.height_safety
            and (args.max_lines <= 0 or row["line_count"] <= args.max_lines)
        )

    low, high, best = args.min_pt, args.max_pt, None
    for _ in range(18):
        point = (low + high) / 2.0
        row = measure(args.text, point, font_path, px_per_pt, box_w,
                      args.line_spacing, args.width_safety, args.render_fudge)
        if fits(row):
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
        "fits": fits(best),
        "utilization": {
            "width": round(best["width_px"] / box_w, 4) if box_w else 0.0,
            "height": round(best["height_px"] / box_h, 4) if box_h else 0.0,
        },
    })
    if args.target_pt is not None:
        target = measure(args.text, args.target_pt, font_path, px_per_pt, box_w,
                         args.line_spacing, args.width_safety, args.render_fudge)
        target["fits"] = fits(target)
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
        "line_spacing": args.line_spacing,
        "width_safety": args.width_safety,
        "height_safety": args.height_safety,
        "render_fudge": args.render_fudge,
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
    parser.add_argument("--font", default="Microsoft YaHei")
    parser.add_argument("--font-file")
    parser.add_argument("--bold", action="store_true")
    parser.add_argument("--min-pt", type=float, default=8)
    parser.add_argument("--max-pt", type=float, default=36)
    parser.add_argument("--max-lines", type=int, default=0)
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
