#!/usr/bin/env python3
"""Compose an editable PPTX through the repository's authoring backend.

The command-line contract remains compatible with the historical composer.
Deck loading/component expansion, native object authoring, asset placement,
preview rendering, atomic output and font embedding now live in focused
modules so the entrypoint only coordinates the workflow.

Usage:
    python3 scripts/compose_pptx.py deck.json out.pptx
    python3 scripts/compose_pptx.py deck.json out.pptx --preview-dir out/preview
    python3 scripts/compose_pptx.py deck.json out.pptx --font-dir project-fonts --embed-fonts
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from asset_placement import replace_svg_media as _replace_svg_media
from asset_placement import svg_to_png as _svg_to_png
from authoring_backend import build_pptx, build_with_embedded_fonts
from component_expander import _choose_slide_layout, _expand_components, _frac, _load_deck, _promote_native_structures, _resolve
from preview_renderer import find_cjk_font as _find_cjk_font
from preview_renderer import render_previews
from reference_preflight import validate_reference_preflight
from pptx_primitives import (
    _add_outer_shadow,
    _apply_shape_fill,
    _hex_to_rgb,
    _hex_to_rgba,
    _hex_to_tuple,
    _set_fill_alpha,
    _set_gradient_fill,
    _set_run_alpha,
    _set_run_fonts,
    text_size_pt as _text_size_pt,
)


def _die(message: str, code: int = 2):
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", help="deck.json / layout.json path.")
    parser.add_argument("out", help="Output .pptx path.")
    parser.add_argument("--preview-dir", help="If set, also render PNG previews here for QA.")
    parser.add_argument("--font-dir", help="Task-local licensed font directory; also used by previews.")
    parser.add_argument("--font-manifest", help="Font manifest; defaults to FONT_DIR/font-manifest.json.")
    parser.add_argument("--embed-fonts", action="store_true", help="Post-process the generated PPTX with OOXML font parts.")
    parser.add_argument("--embedding-report", help="JSON report for the OOXML font embedding step.")
    parser.add_argument("--strict-input", action="store_true", help="reject implicit primitive types, unsupported alignments and out-of-slide geometry")
    parser.add_argument("--require-native-structure", action="store_true", help="require native panels/tables and forbid semantic full-slide frame pictures")
    args = parser.parse_args()

    layout_path = Path(args.layout)
    if not layout_path.exists():
        _die(f"layout file not found: {layout_path}")
    deck = _promote_native_structures(_load_deck(layout_path))
    deck = _expand_components(deck)
    deck["strict_input"] = bool(args.strict_input)
    deck["require_native_structure"] = bool(args.require_native_structure or (args.strict_input and deck.get("editable_object_policy") == "native-semantic-objects"))
    output_path = Path(args.out).resolve()
    if args.font_dir:
        deck["font_dir"] = str(Path(args.font_dir).resolve())

    preflight = validate_reference_preflight(
        layout_path,
        deck,
        embed_fonts=bool(args.embed_fonts),
        font_dir=args.font_dir,
        font_manifest=args.font_manifest,
    )
    if not preflight.get("valid", False):
        issue_codes = ", ".join(str(item.get("code")) for item in preflight.get("issues", []))
        _die(f"reference reconstruction preflight failed: {issue_codes}")

    if args.embed_fonts:
        font_dir = args.font_dir or deck.get("font_dir")
        font_manifest = args.font_manifest or deck.get("font_manifest")
        if not font_dir and not font_manifest:
            _die("--embed-fonts requires --font-dir or --font-manifest")
        try:
            build_with_embedded_fonts(
                deck,
                output_path,
                font_dir=font_dir,
                font_manifest=font_manifest,
                embedding_report=Path(args.embedding_report).resolve() if args.embedding_report else None,
            )
        except (KeyError, OSError, TypeError, ValueError) as exc:
            _die(f"authoring failed: {type(exc).__name__}: {exc}")
    else:
        try:
            build_pptx(deck, output_path)
        except (KeyError, OSError, TypeError, ValueError) as exc:
            _die(f"authoring failed: {type(exc).__name__}: {exc}")
    if args.preview_dir:
        render_previews(deck, Path(args.preview_dir))


if __name__ == "__main__":
    main()
