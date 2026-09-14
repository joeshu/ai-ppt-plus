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
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from asset_placement import replace_svg_media as _replace_svg_media
from asset_placement import svg_to_png as _svg_to_png
from component_expander import _choose_slide_layout, _expand_components, _frac, _load_deck, _resolve
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
from validate_semantic_layout import validate as validate_semantic_layout

SCRIPT_DIR = Path(__file__).resolve().parent


def _manifest_font_paths(manifest_path: str | Path | None) -> list[Path]:
    """Resolve existing font files declared by a task-local manifest."""
    if not manifest_path:
        return []
    path = Path(manifest_path).resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    candidates = []
    declared = manifest.get("file") if isinstance(manifest, dict) else None
    if isinstance(declared, str) and declared.strip():
        candidates.append(declared)
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if isinstance(files, list):
        candidates.extend(item.get("file") for item in files if isinstance(item, dict) and isinstance(item.get("file"), str))
    result = []
    for item in candidates:
        candidate = Path(item)
        resolved = (candidate if candidate.is_absolute() else path.parent / candidate).resolve()
        if resolved.is_file() and resolved not in result:
            result.append(resolved)
    return result


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
    parser.add_argument(
        "--authoring-backend",
        choices=("python-pptx", "artifact-tool"),
        default="python-pptx",
        help="authoring engine; artifact-tool is the strict JavaScript ESM route",
    )
    parser.add_argument("--node", help="Node executable for --authoring-backend artifact-tool")
    parser.add_argument("--node-modules", help="bundled node_modules directory for --authoring-backend artifact-tool")
    parser.add_argument("--strict-input", action="store_true", help="reject implicit primitive types, unsupported alignments and out-of-slide geometry")
    args = parser.parse_args()

    layout_path = Path(args.layout)
    if not layout_path.exists():
        _die(f"layout file not found: {layout_path}")
    deck = _expand_components(_load_deck(layout_path))
    semantic_report = validate_semantic_layout(deck)
    if not semantic_report.get("valid", False):
        issue_codes = ", ".join(str(item.get("code")) for item in semantic_report.get("issues", []))
        _die(f"semantic layout preflight failed: {issue_codes}")
    deck["strict_input"] = bool(args.strict_input)
    output_path = Path(args.out).resolve()
    if args.font_dir:
        deck["font_dir"] = str(Path(args.font_dir).resolve())
    effective_font_dir = str(Path(args.font_dir).resolve()) if args.font_dir else deck.get("font_dir")
    effective_font_manifest = str(Path(args.font_manifest).resolve()) if args.font_manifest else deck.get("font_manifest")

    if args.authoring_backend == "artifact-tool":
        if args.embed_fonts:
            _die("--embed-fonts is only supported by the historical compatibility backend; use the Artifact Tool's registered fonts for strict authoring")
        builder = (Path(__file__).resolve().parents[1] / "ai-ppt-editable" / "scripts" / "artifact_tool_authoring.mjs").resolve()
        if not builder.is_file():
            _die(f"strict authoring builder not found: {builder}")
        node_value = args.node or os.environ.get("CODEX_PRIMARY_RUNTIME_NODE") or shutil.which("node") or shutil.which("node.exe")
        if not node_value:
            _die("Artifact Tool strict authoring requires Node; pass --node or set CODEX_PRIMARY_RUNTIME_NODE")
        node_path = Path(node_value).resolve()
        if not node_path.is_file():
            _die(f"Node executable not found: {node_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        report_path = output_path.with_name(f"{output_path.stem}.artifact-tool.json")
        inspect_path = output_path.with_name(f"{output_path.stem}.artifact-tool.inspect.ndjson")
        with tempfile.TemporaryDirectory(prefix=f".{output_path.stem}-artifact-tool-", dir=str(output_path.parent)) as staging:
            normalized_layout = Path(staging) / "layout.json"
            normalized_layout.write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            command = [
                str(node_path), str(builder), "--layout", str(normalized_layout), "--output", str(output_path),
                "--report", str(report_path), "--inspect", str(inspect_path),
            ]
            if args.node_modules:
                command.extend(["--node-modules", str(Path(args.node_modules).resolve())])
            if effective_font_dir:
                theme_data = deck.get("theme") if isinstance(deck.get("theme"), dict) else {}
                command.extend(["--font-dir", str(Path(effective_font_dir).resolve()), "--font-family", str(theme_data.get("font") or deck.get("font_family") or "Microsoft YaHei")])
            elif effective_font_manifest:
                theme_data = deck.get("theme") if isinstance(deck.get("theme"), dict) else {}
                family = str(theme_data.get("font") or deck.get("font_family") or "Microsoft YaHei")
                manifest_fonts = _manifest_font_paths(effective_font_manifest)
                if not manifest_fonts:
                    _die("Artifact Tool strict authoring could not resolve any existing font file from --font-manifest; pass --font-dir")
                for font_path in manifest_fonts:
                    command.extend(["--font-path", str(font_path), family])
            if args.preview_dir:
                command.extend(["--preview-dir", str(Path(args.preview_dir).resolve())])
            if args.strict_input:
                command.append("--strict-input")
            completed = subprocess.run(command, cwd=str(builder.parent), capture_output=True, text=True, check=False)
            if completed.stdout:
                print(completed.stdout, end="")
            if completed.returncode != 0:
                if completed.stderr:
                    print(completed.stderr, file=sys.stderr, end="")
                _die(f"Artifact Tool strict authoring failed with exit code {completed.returncode}")
        return

    # Keep the historical backend import lazy: the strict route above should
    # load only the ESM adapter and never create or rewrite a deck through the
    # compatibility implementation.
    from authoring_backend import build_pptx, build_with_embedded_fonts

    if args.embed_fonts:
        font_dir = effective_font_dir
        font_manifest = effective_font_manifest
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
