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
import json
import sys
from pathlib import Path

from asset_placement import replace_svg_media as _replace_svg_media
from asset_placement import svg_to_png as _svg_to_png
from authoring_backend import build_pptx, build_with_embedded_fonts
from component_expander import _choose_slide_layout, _expand_components, _frac, _load_deck, _resolve
from perfect_first_adapter import ContractError, prepare_deck
from preview_renderer import find_cjk_font as _find_cjk_font
from preview_renderer import render_previews
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
    parser.add_argument("--chart-manifest", help="independent chart-reconstruction.json; verified native records are promoted before composition")
    parser.add_argument("--gradient-manifest", help="independent gradient-visual-manifest.json")
    parser.add_argument("--adapter-report", help="perfect-first adapter contract report")
    parser.add_argument("--gradient-report", help="inline and manifest gradient contract report")
    parser.add_argument("--typography-report", help="layout-bound typography contract report")
    args = parser.parse_args()

    layout_path = Path(args.layout)
    if not layout_path.exists():
        _die(f"layout file not found: {layout_path}")
    deck = _expand_components(_load_deck(layout_path))
    deck["strict_input"] = bool(args.strict_input)
    output_path = Path(args.out).resolve()
    if args.font_dir:
        deck["font_dir"] = str(Path(args.font_dir).resolve())

    chart_manifest = Path(args.chart_manifest).resolve() if args.chart_manifest else None
    gradient_manifest = Path(args.gradient_manifest).resolve() if args.gradient_manifest else None
    font_dir = Path(deck["font_dir"]).resolve() if deck.get("font_dir") else None
    font_manifest = Path(args.font_manifest).resolve() if args.font_manifest else None
    if font_manifest is None and font_dir is not None and (font_dir / "font-manifest.json").is_file():
        font_manifest = font_dir / "font-manifest.json"
    try:
        deck, adapter_report = prepare_deck(
            deck,
            chart_manifest=chart_manifest,
            gradient_manifest=gradient_manifest,
            font_dir=font_dir,
            font_manifest=font_manifest,
            strict=bool(args.strict_input),
        )
    except (ContractError, OSError, ValueError, json.JSONDecodeError) as exc:
        _die(f"perfect-first contract failed: {type(exc).__name__}: {exc}")
    if args.adapter_report:
        from atomic_output import atomic_write_json
        atomic_write_json(Path(args.adapter_report).resolve(), adapter_report)
    if args.gradient_report:
        from atomic_output import atomic_write_json
        atomic_write_json(Path(args.gradient_report).resolve(), adapter_report["gradients"])
    if args.typography_report:
        from atomic_output import atomic_write_json
        atomic_write_json(Path(args.typography_report).resolve(), adapter_report["typography"])

    if args.embed_fonts:
        font_dir = args.font_dir or deck.get("font_dir")
        # An explicit font directory owns its sibling manifest.  Passing a
        # relative manifest from the layout here used to resolve it against
        # the repository CWD (and could even override the directory's valid
        # manifest), making portable layouts fail outside that CWD.  Let
        # load_specs discover FONT_DIR/font-manifest.json unless the caller
        # explicitly supplied a manifest.
        font_manifest = args.font_manifest or (None if args.font_dir else deck.get("font_manifest"))
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
