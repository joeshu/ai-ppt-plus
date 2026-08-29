#!/usr/bin/env python3
"""Optional Pillow preview renderer for a composed deck specification."""
from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

from asset_placement import cleanup_temporary_files, svg_to_png
from atomic_output import atomic_write_bytes
from component_expander import _frac, _resolve
from pptx_primitives import _hex_to_rgba, _hex_to_tuple, text_size_pt


def find_cjk_font(font_dir=None, bold=False):
    if font_dir:
        local = sorted(Path(font_dir).glob("*.ttf")) + sorted(Path(font_dir).glob("*.otf")) + sorted(Path(font_dir).glob("*.ttc"))
        if local:
            if bold:
                bold_local = [path for path in local if any(token in path.stem.casefold() for token in ("bold", "medium", "semibold"))]
                if bold_local:
                    return str(bold_local[0])
                # Do not silently treat a regular file as a bold face.  The
                # caller can then apply a small synthetic stroke, keeping the
                # preview's weight closer to the native PPTX when a licensed
                # bold companion is not available.
                return None
            return str(local[0])
    candidates_bold = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    ]
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates_bold + candidates if bold else candidates:
        if Path(candidate).exists():
            return candidate
    return None


def _poly_points(shape_type, x0, y0, x1, y1):
    """Approximate polygon vertices for preview rendering of non-rect shapes."""
    width, height = x1 - x0, y1 - y0
    if shape_type == "triangle":
        return [(x0 + width / 2, y0), (x1, y1), (x0, y1)]
    if shape_type == "diamond":
        return [(x0 + width / 2, y0), (x1, y0 + height / 2), (x0 + width / 2, y1), (x0, y0 + height / 2)]
    if shape_type == "right_arrow":
        margin = height * 0.30
        return [(x0, y0 + margin), (x1 - width * 0.4, y0 + margin), (x1 - width * 0.4, y0), (x1, y0 + height / 2), (x1 - width * 0.4, y1), (x1 - width * 0.4, y1 - margin), (x0, y1 - margin)]
    if shape_type == "left_arrow":
        margin = height * 0.30
        return [(x1, y0 + margin), (x0 + width * 0.4, y0 + margin), (x0 + width * 0.4, y0), (x0, y0 + height / 2), (x0 + width * 0.4, y1), (x0 + width * 0.4, y1 - margin), (x1, y1 - margin)]
    if shape_type == "up_arrow":
        margin = width * 0.30
        return [(x0 + margin, y1), (x0 + margin, y0 + height * 0.4), (x0, y0 + height * 0.4), (x0 + width / 2, y0), (x1, y0 + height * 0.4), (x1 - margin, y0 + height * 0.4), (x1 - margin, y1)]
    if shape_type == "chevron":
        notch = width * 0.25
        return [(x0, y0), (x1 - notch, y0), (x1, y0 + height / 2), (x1 - notch, y1), (x0, y1), (x0 + notch, y0 + height / 2)]
    if shape_type == "trapezoid":
        inset = width * 0.22
        return [(x0 + inset, y0), (x1 - inset, y0), (x1, y1), (x0, y1)]
    if shape_type == "parallelogram":
        skew = width * 0.22
        return [(x0 + skew, y0), (x1, y0), (x1 - skew, y1), (x0, y1)]
    if shape_type == "pentagon":
        import math

        center_x, center_y = x0 + width / 2, y0 + height / 2
        radius_x, radius_y = width / 2, height / 2
        return [(center_x + radius_x * math.sin(2 * math.pi * i / 5), center_y - radius_y * math.cos(2 * math.pi * i / 5)) for i in range(5)]
    if shape_type == "hexagon":
        return [(x0 + width * 0.25, y0), (x0 + width * 0.75, y0), (x1, y0 + height / 2), (x0 + width * 0.75, y1), (x0 + width * 0.25, y1), (x0, y0 + height / 2)]
    return None


def _wrap_text(draw, text, font, max_width):
    output = []
    for raw in text.split("\n"):
        if not raw:
            output.append("")
            continue
        line = ""
        for character in raw:
            trial = line + character
            if draw.textlength(trial, font=font) > max_width and line:
                output.append(line)
                line = character
            else:
                line = trial
        output.append(line)
    return output


def _open_asset(path: Path, temporary_files: list[Path]) -> Path:
    if path.suffix.casefold() == ".svg":
        return svg_to_png(path, temporary_files)
    return path


def render_previews(deck: dict, preview_dir: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Preview skipped: Pillow not available.", file=sys.stderr)
        return

    assets_dir = Path(deck["assets_dir"])
    slide_width = float(deck["slide_width_in"])
    slide_height = float(deck["slide_height_in"])
    ratio = slide_width / slide_height
    if deck["units"] == "px" and deck.get("ref_width") and deck.get("ref_height"):
        # Reference screenshots can carry a few pixels of capture padding and
        # therefore not have the slide's declared aspect ratio.  The preview
        # must still use the slide ratio or preview-consistency will reject a
        # valid reconstruction even though the final PPTX renders correctly.
        canvas_height = int(deck["ref_height"])
        canvas_width = max(1, int(round(canvas_height * ratio)))
    else:
        canvas_width = 1600
        canvas_height = int(round(canvas_width / ratio))
    slide_height_pt = slide_height * 72.0
    ref_width = float(deck.get("ref_width") or canvas_width)
    ref_height = float(deck.get("ref_height") or canvas_height)
    preview_dir.mkdir(parents=True, exist_ok=True)
    regular_path = find_cjk_font(deck.get("font_dir"), bold=False)
    bold_path = find_cjk_font(deck.get("font_dir"), bold=True)
    temporary_files: list[Path] = []

    try:
        for index, slide_spec in enumerate(deck["slides"], 1):
            canvas = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 255))
            background = slide_spec.get("background")
            if background:
                path = _resolve(assets_dir, background)
                if path.exists():
                    with Image.open(path) as image:
                        canvas.paste(image.convert("RGBA").resize((canvas_width, canvas_height)), (0, 0))

            frame = slide_spec.get("frame")
            if frame:
                path = _resolve(assets_dir, frame)
                if path.exists():
                    with Image.open(path) as image:
                        canvas.alpha_composite(image.convert("RGBA").resize((canvas_width, canvas_height)), (0, 0))

            # Semantic panel images are structural substrates.  Render them
            # before native overlays so this diagnostic preview follows the
            # PPTX backend: badges, legend keys and bullet marks remain
            # visible instead of being covered by their panel image.
            for panel in slide_spec.get("panels", []):
                path = _resolve(assets_dir, panel["file"])
                if not path.exists():
                    continue
                fx = _frac(deck, panel, "x", "x", ref_width)
                fy = _frac(deck, panel, "y", "y", ref_height)
                fw = _frac(deck, panel, "w", "x", ref_width)
                fh = _frac(deck, panel, "h", "y", ref_height)
                with Image.open(path) as image:
                    panel_image = image.convert("RGBA").resize((max(1, int(fw * canvas_width)), max(1, int(fh * canvas_height))))
                canvas.alpha_composite(panel_image, (int(fx * canvas_width), int(fy * canvas_height)))

            for shape_spec in slide_spec.get("shapes", []):
                fx = _frac(deck, shape_spec, "x", "x", ref_width)
                fy = _frac(deck, shape_spec, "y", "y", ref_height)
                x0, y0 = int(fx * canvas_width), int(fy * canvas_height)
                overlay = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)
                shape_type = shape_spec.get("type", "rounded_rect")
                if shape_type == "line" and "x2" in shape_spec and "y2" in shape_spec:
                    x1 = int(_frac(deck, shape_spec, "x2", "x", ref_width) * canvas_width)
                    y1 = int(_frac(deck, shape_spec, "y2", "y", ref_height) * canvas_height)
                else:
                    fw = _frac(deck, shape_spec, "w", "x", ref_width)
                    fh = _frac(deck, shape_spec, "h", "y", ref_height)
                    x1, y1 = int((fx + fw) * canvas_width), int((fy + fh) * canvas_height)
                alpha = int(float(shape_spec.get("opacity", 1.0)) * 255) if shape_spec.get("fill") else 0
                fill = _hex_to_tuple(shape_spec["fill"]) + (alpha,) if shape_spec.get("fill") else None
                line = _hex_to_tuple(shape_spec["line"]) + (255,) if shape_spec.get("line") else None
                line_width = int(round(float(shape_spec.get("line_width", 1.0)) * canvas_height / (slide_height * 72.0)))
                line_width = max(1, line_width) if line else 0
                polygon = _poly_points(shape_type, x0, y0, x1, y1)
                if shape_type == "line":
                    draw.line([x0, y0, x1, y1], fill=line or (255, 255, 255, 255), width=max(1, line_width or 2))
                elif shape_type in ("oval", "ellipse"):
                    draw.ellipse([x0, y0, x1, y1], fill=fill, outline=line, width=line_width)
                elif shape_type == "rounded_rect":
                    radius = int(float(shape_spec.get("radius", 0.12)) * min(x1 - x0, y1 - y0))
                    draw.rounded_rectangle([x0, y0, x1, y1], radius=max(1, radius), fill=fill, outline=line, width=line_width)
                elif polygon is not None:
                    draw.polygon(polygon, fill=fill, outline=line, width=line_width)
                else:
                    draw.rectangle([x0, y0, x1, y1], fill=fill, outline=line, width=line_width)
                canvas.alpha_composite(overlay)

            for icon in slide_spec.get("icons", []):
                path = _resolve(assets_dir, icon["file"])
                if not path.exists():
                    continue
                path = _open_asset(path, temporary_files)
                fx = _frac(deck, icon, "x", "x", ref_width)
                fy = _frac(deck, icon, "y", "y", ref_height)
                fw = _frac(deck, icon, "w", "x", ref_width)
                fh = _frac(deck, icon, "h", "y", ref_height)
                with Image.open(path) as image:
                    icon_image = image.convert("RGBA").resize((max(1, int(fw * canvas_width)), max(1, int(fh * canvas_height))))
                canvas.alpha_composite(icon_image, (int(fx * canvas_width), int(fy * canvas_height)))

            draw = ImageDraw.Draw(canvas)
            for text_spec in slide_spec.get("texts", []):
                fx = _frac(deck, text_spec, "x", "x", ref_width)
                fy = _frac(deck, text_spec, "y", "y", ref_height)
                fw = _frac(deck, text_spec, "w", "x", ref_width)
                size_pt = text_size_pt(text_spec, slide_height_pt, ref_height)
                pixel_size = max(8, int(round(size_pt * canvas_height / slide_height_pt)))
                bold = bool(text_spec.get("bold", False))
                font_path = (bold_path if bold else regular_path) or regular_path
                try:
                    font = ImageFont.truetype(font_path, pixel_size) if font_path else ImageFont.load_default()
                except Exception:
                    font = ImageFont.load_default()
                color = text_spec.get("color", "#111111")
                align = text_spec.get("align", "left")
                valign = text_spec.get("valign", "top")
                opacity = float(text_spec.get("opacity", 1.0))
                box_x, box_y = int(fx * canvas_width), int(fy * canvas_height)
                box_width = int(fw * canvas_width)
                box_height = int(_frac(deck, text_spec, "h", "y", ref_height) * canvas_height)
                line_height = int(pixel_size * 1.3)
                runs = text_spec.get("runs")
                if runs:
                    characters = []
                    for run_spec in runs:
                        run_bold = bool(run_spec.get("bold", bold))
                        run_size = max(8, int(round(text_size_pt(run_spec, slide_height_pt, ref_height, default=size_pt) * canvas_height / slide_height_pt)))
                        run_path = (bold_path if run_bold else regular_path) or regular_path
                        try:
                            run_font = ImageFont.truetype(run_path, run_size) if run_path else ImageFont.load_default()
                        except Exception:
                            run_font = ImageFont.load_default()
                        for character in str(run_spec.get("text", "")):
                            characters.append((character, run_font, run_spec.get("color", color), float(run_spec.get("opacity", opacity)), run_bold))
                    lines, line, line_width = [], [], 0.0
                    for character, character_font, character_color, character_opacity, character_bold in characters:
                        if character == "\n":
                            lines.append(line)
                            line, line_width = [], 0.0
                            continue
                        character_width = draw.textlength(character, font=character_font)
                        if line and line_width + character_width > box_width:
                            lines.append(line)
                            line, line_width = [], 0.0
                        line.append((character, character_font, character_color, character_opacity, character_bold, character_width))
                        line_width += character_width
                    if line or not lines:
                        lines.append(line)
                    total_height = line_height * len(lines)
                    text_y = box_y + (max(0, box_height - total_height) if valign == "bottom" else max(0, (box_height - total_height) // 2) if valign in ("middle", "center") else 0)
                    for line_index, line_items in enumerate(lines):
                        total_width = sum(item[5] for item in line_items)
                        cursor_x = box_x + (box_width - total_width if align == "right" else (box_width - total_width) / 2 if align == "center" else 0)
                        for character, character_font, character_color, character_opacity, character_bold, character_width in line_items:
                            stroke = 1 if character_bold and not bold_path else 0
                            fill = _hex_to_rgba(character_color, character_opacity)
                            draw.text((max(box_x, int(cursor_x)), text_y + line_index * line_height), character, fill=fill, font=character_font, stroke_width=stroke, stroke_fill=fill)
                            cursor_x += character_width
                else:
                    lines = _wrap_text(draw, str(text_spec.get("text", "")), font, max(1, box_width))
                    total_height = line_height * max(1, len(lines))
                    text_y = box_y + (max(0, box_height - total_height) if valign == "bottom" else max(0, (box_height - total_height) // 2) if valign in ("middle", "center") else 0)
                    stroke = 1 if bold and not bold_path else 0
                    for line_index, line in enumerate(lines):
                        line_width = draw.textlength(line, font=font)
                        text_x = box_x + (box_width - line_width if align == "right" else (box_width - line_width) / 2 if align == "center" else 0)
                        fill = _hex_to_rgba(color, opacity)
                        draw.text((max(box_x, int(text_x)), text_y + line_index * line_height), line, fill=fill, font=font, stroke_width=stroke, stroke_fill=fill)

            output = preview_dir / f"slide_{index:02d}.png"
            buffer = BytesIO()
            canvas.convert("RGB").save(buffer, format="PNG")
            atomic_write_bytes(output, buffer.getvalue(), suffix=".tmp.png")
            print(f"Preview: {output}")
    finally:
        cleanup_temporary_files(temporary_files)
