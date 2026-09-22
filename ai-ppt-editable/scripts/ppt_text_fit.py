#!/usr/bin/env python3
"""Preflight editable PowerPoint text with real runtime font metrics.

The fitter preserves reference line topology when supplied. It uses the same
runtime-resolved font family that authoring should use and reports geometry
shortfalls instead of silently shrinking typography to compensate for a wrong
text slot.
"""
from __future__ import annotations

import argparse
import copy
import functools
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
_NO_LINE_START = set("，。！？；：、）》】〕〉」』”’…—％%℃°)]}")
_NO_LINE_END = set("《【〔〈「『“‘（([{<")

_ROLE_DEFAULTS = {
    "hero_title": {"min_pt": 24.0, "min_scale": 0.90},
    "title": {"min_pt": 20.0, "min_scale": 0.90},
    "section_title": {"min_pt": 15.0, "min_scale": 0.88},
    "body": {"min_pt": 10.0, "min_scale": 0.82},
    "caption": {"min_pt": 8.0, "min_scale": 0.78},
}

_DECK_MEASUREMENT_CACHE: dict[tuple, dict] = {}
_DECK_MEASUREMENT_CACHE_MAX = 4096
_DECK_CACHE_HITS = 0
_DECK_CACHE_MISSES = 0


def clear_measurement_cache() -> None:
    """Clear process-wide deck measurement state (mainly for tests/benchmarks)."""
    global _DECK_CACHE_HITS, _DECK_CACHE_MISSES
    _DECK_MEASUREMENT_CACHE.clear()
    _DECK_CACHE_HITS = 0
    _DECK_CACHE_MISSES = 0


def measurement_cache_info() -> dict:
    return {"size": len(_DECK_MEASUREMENT_CACHE), "hits": _DECK_CACHE_HITS, "misses": _DECK_CACHE_MISSES}


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


@functools.lru_cache(maxsize=512)
def _font(path: str, pixels: int) -> ImageFont.FreeTypeFont:
    """Reuse FreeType objects across slots in a deck-level audit."""
    return ImageFont.truetype(path, max(1, pixels))


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


def _rebalance_title_orphan(lines: list[str], draw: ImageDraw.ImageDraw,
                            font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """Avoid a single CJK glyph on the last title line when geometry permits."""
    if len(lines) < 2 or len(lines[-1].strip()) != 1 or len(lines[-2].strip()) < 3:
        return lines
    moved = lines[-2][-1] + lines[-1]
    previous = lines[-2][:-1].rstrip()
    if previous and _width(draw, font, moved) <= max_width:
        return [*lines[:-2], previous, moved]
    return lines


def wrap(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, text: str,
         max_width: float, *, avoid_single_cjk_orphan: bool = False) -> list[str]:
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
    result = [line for line in lines if line] or [""]
    if avoid_single_cjk_orphan:
        result = _rebalance_title_orphan(result, draw, font, max_width)
    return result


def measure(text: str, pt: float, font_path: Path, px_per_pt: float, width_px: float,
            line_spacing: float, width_safety: float, render_fudge: float,
            *, avoid_single_cjk_orphan: bool = False) -> dict:
    font_px = max(1, int(round(pt * px_per_pt * render_fudge)))
    font = _font(str(font_path), font_px)
    draw = ImageDraw.Draw(Image.new("RGB", (max(4, int(width_px * 2)), 4096), "white"))
    lines: list[str] = []
    for paragraph in _paragraphs(text):
        lines.extend(wrap(draw, font, paragraph, width_px * width_safety,
                          avoid_single_cjk_orphan=avoid_single_cjk_orphan))
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


def measure_rich(runs: list[dict], pt: float, font_path: Path, px_per_pt: float,
                 width_px: float, line_spacing: float, width_safety: float,
                 render_fudge: float, *, target_pt: float | None = None) -> dict:
    """Measure mixed CJK/Latin rich text using each run's actual face and size.

    The run size scales with the candidate point size, so binary fitting keeps
    relative hierarchy (for example a large number plus a smaller unit).
    Superscript/subscript uses PowerPoint-like reduced glyphs while increasing
    line extent for the baseline shift.
    """
    draw = ImageDraw.Draw(Image.new("RGB", (max(4, int(width_px * 2)), 4096), "white"))
    scale = pt / target_pt if target_pt and target_pt > 0 else 1.0
    styled_tokens: list[tuple[str, ImageFont.FreeTypeFont, float]] = []
    for run in runs:
        content = str(run.get("text", run.get("content", "")))
        style = run.get("style") if isinstance(run.get("style"), dict) else {}
        size = float(run.get("font_size_pt") or run.get("size_pt") or run.get("size") or
                     style.get("font_size_pt") or style.get("size_pt") or style.get("size") or pt)
        baseline = str(run.get("baseline") or style.get("baseline") or "normal").lower()
        if baseline in {"superscript", "subscript", "super", "sub"}:
            size *= 0.65
        run_font_name = str(run.get("font") or run.get("font_family") or style.get("font") or style.get("font_family") or "")
        run_bold = bool(run.get("bold", style.get("bold", False)))
        run_path = find_font(run_font_name, run_bold) if run_font_name else font_path
        pixels = max(1, int(round(size * scale * px_per_pt * render_fudge)))
        run_font = _font(str(run_path), pixels)
        extent_factor = 1.22 if baseline in {"superscript", "subscript", "super", "sub"} else 1.0
        for paragraph_index, paragraph in enumerate(_paragraphs(content)):
            if paragraph_index:
                styled_tokens.append(("\n", run_font, extent_factor))
            styled_tokens.extend((token, run_font, extent_factor) for token in _tokens(paragraph))

    max_width = width_px * width_safety
    lines: list[list[tuple[str, ImageFont.FreeTypeFont, float]]] = [[]]
    line_widths = [0.0]
    for token, token_font, extent in styled_tokens:
        if token == "\n":
            lines.append([]); line_widths.append(0.0); continue
        token_width = _width(draw, token_font, token)
        if lines[-1] and line_widths[-1] + token_width > max_width:
            lines.append([]); line_widths.append(0.0)
        if token_width > max_width:
            for char in token:
                char_width = _width(draw, token_font, char)
                if lines[-1] and line_widths[-1] + char_width > max_width:
                    lines.append([]); line_widths.append(0.0)
                lines[-1].append((char, token_font, extent)); line_widths[-1] += char_width
        else:
            lines[-1].append((token, token_font, extent)); line_widths[-1] += token_width
    line_heights = []
    for line in lines:
        heights = []
        for token, token_font, extent in line:
            box = draw.textbbox((0, 0), token or "口", font=token_font)
            heights.append(max(box[3] - box[1], token_font.size * 0.82) * extent)
        line_heights.append(max(heights, default=max(1, int(pt * px_per_pt * 0.82))))
    plain_lines = ["".join(token for token, _, _ in line).rstrip() for line in lines]
    return {
        "pt": pt,
        "font_px": max((font.size for line in lines for _, font, _ in line), default=1),
        "lines": plain_lines or [""],
        "line_count": len(plain_lines) or 1,
        "width_px": max(line_widths, default=0.0),
        "height_px": sum(line_heights) * line_spacing,
        "line_height_px": max(line_heights, default=0.0) * line_spacing,
        "occupied_glyph_proxy_px2": sum(line_widths) * max(line_heights, default=1.0),
        "rich_text_measured": True,
        "run_count": len(runs),
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
    rich_runs = getattr(args, "rich_runs", None)
    run_signature = json.dumps(rich_runs, ensure_ascii=False, sort_keys=True, default=str) if rich_runs else None
    cache_hits_before = _DECK_CACHE_HITS
    cache_misses_before = _DECK_CACHE_MISSES

    def evaluate(point: float) -> dict:
        global _DECK_CACHE_HITS, _DECK_CACHE_MISSES
        key = round(float(point), 4)
        if key not in measurement_cache:
            deck_key = (
                str(args.text), run_signature, key, str(font_path), round(px_per_pt, 6),
                round(box_w, 3), round(args.line_spacing, 4), round(args.width_safety, 4),
                round(args.render_fudge, 4), semantic_role, round(target_pt or 0.0, 3),
            )
            if deck_key in _DECK_MEASUREMENT_CACHE:
                _DECK_CACHE_HITS += 1
                measurement_cache[key] = copy.deepcopy(_DECK_MEASUREMENT_CACHE[deck_key])
                return measurement_cache[key]
            _DECK_CACHE_MISSES += 1
            if isinstance(rich_runs, list) and rich_runs:
                row = measure_rich(
                    rich_runs, key, font_path, px_per_pt, box_w,
                    args.line_spacing, args.width_safety, args.render_fudge,
                    target_pt=target_pt,
                )
            else:
                row = measure(
                    args.text, key, font_path, px_per_pt, box_w,
                    args.line_spacing, args.width_safety, args.render_fudge,
                    avoid_single_cjk_orphan=semantic_role in {"hero_title", "title", "section_title"},
                )
            if len(_DECK_MEASUREMENT_CACHE) >= _DECK_MEASUREMENT_CACHE_MAX:
                _DECK_MEASUREMENT_CACHE.pop(next(iter(_DECK_MEASUREMENT_CACHE)))
            _DECK_MEASUREMENT_CACHE[deck_key] = copy.deepcopy(row)
            measurement_cache[key] = row
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
        # Most labels and headings already fit at their requested maximum.
        # One exact probe avoids 18 redundant measurements while preserving
        # the old binary search for genuinely constrained text.
        best = evaluate(args.max_pt)
        search_strategy = "single-probe-max-fit-v1"
        if not geometry_fits(best):
            low, high, best = args.min_pt, args.max_pt, None
            search_strategy = "single-probe-then-binary-v1"
            for _ in range(18):
                point = (low + high) / 2.0
                row = evaluate(point)
                if geometry_fits(row):
                    best, low = row, point
                else:
                    high = point
        if best is None:
            best = evaluate(args.min_pt)
    if args.target_lines > 0:
        search_strategy = "monotonic-boundary-local-refine-v1"

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
        "tokenization": "cjk-kinsoku-paired-punctuation-number-unit-title-orphan-v4",
        "measurement_count": len(measurement_cache),
        "search_strategy": search_strategy,
        "measurement_mode": "rich-runs" if rich_runs else "single-style",
        "deck_measurement_cache": {
            "hits": _DECK_CACHE_HITS - cache_hits_before,
            "misses": _DECK_CACHE_MISSES - cache_misses_before,
            "entries": len(_DECK_MEASUREMENT_CACHE),
        },
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
