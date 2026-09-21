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


TEXT_FIT_SCHEMA = "ai-ppt-plus/text-fit/v2"
_LINE_BREAK_RE = re.compile(r"\r\n?|\n")
# Keep Latin/number/symbol runs together whenever possible.  This is
# deliberately broader than ``\w`` so leading signs, percentages, units,
# dates, ratios, parenthesized values and common currency/degree symbols do
# not become accidental wrap points in a narrow CJK text slot.
_TOKEN_RE = re.compile(
    r"[A-Za-z0-9_./:+#%°$€¥£‰&@()\[\]{}<>–—-]+|\s+|.",
    flags=re.DOTALL,
)

# Conservative Chinese line-breaking rules. A box can technically fit while
# still looking wrong if closing punctuation starts a line or opening
# punctuation ends one.
_NO_LINE_START = set("，。！？；：、）》】〕〉」』”’…—％%℃°")
_NO_LINE_END = set("《【〔〈「『“‘（(")

_ROLE_DEFAULTS = {
    "hero_title": {"min_pt": 24.0, "min_scale": 0.90},
    "title": {"min_pt": 20.0, "min_scale": 0.90},
    "section_title": {"min_pt": 15.0, "min_scale": 0.88},
    "body": {"min_pt": 10.0, "min_scale": 0.82},
    "caption": {"min_pt": 8.0, "min_scale": 0.78},
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
    raw = _TOKEN_RE.findall(str(text))
    tokens: list[str] = []
    index = 0
    while index < len(raw):
        token = raw[index]
        if token in _NO_LINE_START and tokens:
            tokens[-1] += token
        elif token in _NO_LINE_END and index + 1 < len(raw):
            raw[index + 1] = token + raw[index + 1]
        else:
            tokens.append(token)
        index += 1
    return tokens


def _paragraphs(text: str) -> list[str]:
    """Split explicit line breaks without leaving a CR glyph in the text."""
    return _LINE_BREAK_RE.split(str(text))


def _split_overwide(text: str, draw: ImageDraw.ImageDraw,
                    font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """Split only when a token cannot fit as a whole.

    CJK is already tokenized one character at a time.  This fallback is for a
    single long Latin/number run (for example a URL or identifier) that is
    wider than the slot; normal mixed-language runs remain intact.
    """
    fragments: list[str] = []
    current = ""
    for char in text:
        if current and _width(draw, font, current + char) > max_width:
            fragments.append(current)
            current = char
        else:
            current += char
    if current:
        fragments.append(current)
    return fragments or [""]


def wrap(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, text: str, max_width: float) -> list[str]:
    lines: list[str] = []
    current = ""
    for token in _tokens(text):
        candidate = current + token
        if current and _width(draw, font, candidate) > max_width:
            lines.append(current.rstrip())
            current = token.lstrip()
        else:
            current = candidate

        # The previous implementation only split an over-wide token after a
        # line had already been started.  A leading URL, number+unit or
        # symbol-prefixed metric could therefore escape the wrapping logic.
        if current and _width(draw, font, current) > max_width:
            fragments = _split_overwide(current, draw, font, max_width)
            lines.extend(fragment.rstrip() for fragment in fragments[:-1] if fragment.rstrip())
            current = fragments[-1]
    lines.append(current.rstrip())
    return [line for line in lines if line] or [""]


def measure(text: str, pt: float, font_path: Path, px_per_pt: float, width_px: float,
            line_spacing: float, width_safety: float, render_fudge: float) -> dict:
    font_px = max(1, int(round(pt * px_per_pt * render_fudge)))
    font = ImageFont.truetype(str(font_path), font_px)
    draw = ImageDraw.Draw(Image.new("RGB", (max(4, int(width_px * 2)), 4096), "white"))
    lines: list[str] = []
    for paragraph in _paragraphs(text):
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


def _required_box(row: dict, width_safety: float, height_safety: float) -> list[int]:
    return [
        math.ceil(row["width_px"] / max(width_safety, 0.01)),
        math.ceil(row["height_px"] / max(height_safety, 0.01)),
    ]


def _box_deficit(required_box: list[int], box_w: float, box_h: float) -> list[int]:
    return [
        max(0, required_box[0] - math.floor(box_w)),
        max(0, required_box[1] - math.floor(box_h)),
    ]


def _repair_hint(row: dict, deficit: list[int], *, topology_preserved: bool) -> str:
    """Return an actionable diagnostic without turning it into a release gate."""
    if not topology_preserved:
        return "preserve_reference_line_topology"
    if deficit[0] and deficit[1]:
        return "expand_text_slot_width_and_height"
    if deficit[0]:
        return "expand_text_slot_width"
    if deficit[1]:
        return "expand_text_slot_height"
    if not row.get("geometry_fits", False):
        return "expand_text_slot_or_relax_line_limit"
    return "none"


def best_fit(args: argparse.Namespace) -> dict:
    # Internal callers created before exact line-topology support do not yet
    # populate these fields. Keep them valid while the new capability remains
    # opt-in through layout evidence or the CLI.
    if not hasattr(args, "target_lines") or args.target_lines is None:
        args.target_lines = 0
    args.target_lines = max(0, int(args.target_lines or 0))
    if not hasattr(args, "scan_step") or args.scan_step is None:
        args.scan_step = 0.25
    args.scan_step = max(0.10, float(args.scan_step))
    args.max_lines = max(0, int(getattr(args, "max_lines", 0) or 0))
    args.width_safety = max(0.01, float(getattr(args, "width_safety", 0.92) or 0.92))
    args.height_safety = max(0.01, float(getattr(args, "height_safety", 0.95) or 0.95))
    args.line_spacing = max(0.01, float(getattr(args, "line_spacing", 1.06) or 1.06))
    args.render_fudge = max(0.01, float(getattr(args, "render_fudge", 1.01) or 1.01))
    target_pt = getattr(args, "target_pt", None)
    if target_pt is not None:
        target_pt = float(target_pt)
    semantic_role = str(getattr(args, "semantic_role", "body") or "body").strip().lower()
    role_defaults = _ROLE_DEFAULTS.get(semantic_role, _ROLE_DEFAULTS["body"])
    min_readable_pt = float(getattr(args, "min_readable_pt", None) or role_defaults["min_pt"])
    min_hierarchy_scale = float(getattr(args, "min_hierarchy_scale", None) or role_defaults["min_scale"])

    box_w, box_h = _pair(args.box)
    slide_w_px, _ = _pair(args.slide_px)
    slide_w_in, _ = _pair(args.slide_in)
    px_per_pt = (slide_w_px / slide_w_in) / 72.0
    font_path = find_font(args.font, args.bold, args.font_file)

    measurement_cache: dict[float, dict] = {}

    def evaluate(point: float) -> dict:
        key = round(float(point), 4)
        if key not in measurement_cache:
            measurement_cache[key] = measure(
                args.text, key, font_path, px_per_pt, box_w,
                args.line_spacing, args.width_safety, args.render_fudge,
            )
        return measurement_cache[key]

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

    # Find the largest point size whose geometry fits and whose line count does
    # not exceed the reference. This predicate is monotonic for ordinary PPT
    # text flow, unlike equality with an exact line count. Refine only around
    # the discovered boundary instead of scanning the complete font range.
    if args.target_lines > 0:
        low, high = args.min_pt, args.max_pt
        boundary = None
        for _ in range(12):
            point = (low + high) / 2.0
            row = evaluate(point)
            if geometry_fits(row) and row["line_count"] <= args.target_lines:
                boundary, low = row, point
            else:
                high = point

        step = max(0.10, args.scan_step)
        center = boundary["pt"] if boundary is not None else args.min_pt
        local_points = {
            args.min_pt, args.max_pt, center,
            *(
                min(args.max_pt, max(args.min_pt, center + offset * step))
                for offset in range(-4, 5)
            ),
        }
        candidates = [evaluate(point) for point in sorted(local_points, reverse=True)]
        exact = [row for row in candidates if full_fit(row)]
        if exact:
            best = max(exact, key=lambda row: row["pt"])
        else:
            geometrically_valid = [row for row in candidates if geometry_fits(row)] or candidates
            best = min(geometrically_valid, key=lambda row: (
                abs(row["line_count"] - args.target_lines), -row["pt"],
            ))
    else:
        low, high, best = args.min_pt, args.max_pt, None
        for _ in range(18):
            point = (low + high) / 2.0
            row = evaluate(point)
            if geometry_fits(row):
                best, low = row, point
            else:
                high = point
        if best is None:
            best = evaluate(args.min_pt)

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
    best_required_box = _required_box(best, args.width_safety, args.height_safety)
    best_box_deficit = _box_deficit(best_required_box, box_w, box_h)
    best.update({
        "schema": TEXT_FIT_SCHEMA,
        "target_pt": target_pt,
        "target_lines": args.target_lines,
        "required_box_px": best_required_box,
        "box_deficit_px": best_box_deficit,
        "recommended_required_box_px": best_required_box,
        "recommended_box_deficit_px": best_box_deficit,
    })

    if target_pt is not None:
        target = evaluate(target_pt)
        target["fits"] = full_fit(target)
        target["geometry_fits"] = geometry_fits(target)
        target["line_topology_preserved"] = topology_matches(target)
        target["required_box_px"] = _required_box(target, args.width_safety, args.height_safety)
        target["box_deficit_px"] = _box_deficit(target["required_box_px"], box_w, box_h)
        best["target"] = target
        # Top-level geometry evidence is always about the requested/reference
        # typography when it exists.  Recommended-size evidence remains
        # available under the explicitly named fields above.
        best["required_box_px"] = target["required_box_px"]
        best["box_deficit_px"] = target["box_deficit_px"]
        best["reference_scale"] = round(best["recommended_pt"] / target_pt, 4) if target_pt else 1.0

    diagnostic_row = best.get("target") or best
    diagnostic_deficit = diagnostic_row.get("box_deficit_px", best_box_deficit)
    diagnostic_topology = bool(diagnostic_row.get("line_topology_preserved", True))
    reference_pt = target_pt or float(args.max_pt)
    hierarchy_scale = (best["recommended_pt"] / reference_pt) if reference_pt else 1.0
    hierarchy_preserved = (
        best["recommended_pt"] >= min_readable_pt
        and hierarchy_scale >= min_hierarchy_scale
    )
    best.update({
        "target_fits": bool(diagnostic_row.get("fits", best.get("fits"))),
        "repair_policy": "text_slot_first_font_shrink_last",
        "repair_hint": _repair_hint(
            diagnostic_row,
            diagnostic_deficit,
            topology_preserved=diagnostic_topology,
        ),
        "semantic_role": semantic_role,
        "hierarchy_scale": round(hierarchy_scale, 4),
        "hierarchy_preserved": hierarchy_preserved,
        "font_shrink_allowed": hierarchy_preserved,
        "fit_decision": (
            "slot_preserved" if bool(diagnostic_row.get("fits", best.get("fits")))
            else "geometry_repair_required" if not hierarchy_preserved
            else "font_adjustment_candidate"
        ),
        "hierarchy_constraints": {
            "min_readable_pt": min_readable_pt,
            "min_hierarchy_scale": min_hierarchy_scale,
        },
    })
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
        "target_pt": target_pt,
        "runtime_font_required": True,
        "tokenization": "cjk-kinsoku-latin-number-symbol-run-v3",
        "measurement_count": len(measurement_cache),
        "search_strategy": "monotonic-boundary-local-refine-v1",
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
    parser.add_argument("--target-lines", "--reference-line-count", dest="target_lines", type=int, default=0, help="exact observable reference line count; 0 disables exact topology matching")
    parser.add_argument("--scan-step", type=float, default=0.25, help="point-size scan step when --target-lines is used")
    parser.add_argument("--line-spacing", type=float, default=1.06)
    parser.add_argument("--width-safety", type=float, default=0.92)
    parser.add_argument("--height-safety", type=float, default=0.95)
    parser.add_argument("--render-fudge", type=float, default=1.01)
    parser.add_argument("--target-pt", type=float)
    parser.add_argument("--semantic-role", default="body", choices=sorted(_ROLE_DEFAULTS))
    parser.add_argument("--min-readable-pt", type=float)
    parser.add_argument("--min-hierarchy-scale", type=float)
    parser.add_argument("--slide-px", default="1672x941")
    parser.add_argument("--slide-in", default="13.333333x7.505")
    args = parser.parse_args(argv)
    print(json.dumps(best_fit(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
