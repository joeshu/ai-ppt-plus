#!/usr/bin/env python3
"""Compose an editable PPTX through the repository's authoring backend.

The command-line contract remains compatible with the historical composer.
Deck loading/component expansion, native object authoring, asset placement,
preview rendering, atomic output and font embedding now live in focused
modules so the entrypoint only coordinates the workflow.

Strict/reference authoring also runs the full-slot E3 text-fit gate before any
PPTX bytes are authored. The gate implementation lives in
``text_fit_authoring_gate`` so this entrypoint remains orchestration-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from asset_placement import replace_svg_media as _replace_svg_media
from atomic_output import atomic_write_json
from calibrate_page_geometry import apply_page_graph_geometry
from chart_blank_gap_repair import repair_chart_blank_gaps
from asset_placement import svg_to_png as _svg_to_png
from component_expander import _choose_slide_layout, _expand_components, _frac, _load_deck, _promote_native_structures, _resolve
from geometry_authoring import (
    postprocess_authoring_output,
    prepare_cli as prepare_geometry_resolution,
    validate_artifact_tool_binding,
    write_resolution_report,
)
from preview_renderer import find_cjk_font as _find_cjk_font
from preview_renderer import render_previews
from reference_preflight import validate_reference_preflight
from strict_layout_preflight import enforce_reference as enforce_strict_reference_layout
from text_fit_authoring_gate import run_text_fit_e3, text_fit_failure_message, write_text_fit_e4_receipt
from validate_semantic_layout import validate as validate_semantic_layout
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

SCRIPT_DIR = Path(__file__).resolve().parent


def _manifest_font_paths(manifest_path: str | Path | None) -> list[Path]:
    """Resolve manifest-declared or adjacent runtime-managed font files."""
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
    fonts = manifest.get("fonts") if isinstance(manifest, dict) else None
    if isinstance(fonts, list):
        candidates.extend(
            item.get("file") or item.get("path")
            for item in fonts
            if isinstance(item, dict) and isinstance(item.get("file") or item.get("path"), str)
        )
    result = []
    for item in candidates:
        candidate = Path(item)
        resolved = (candidate if candidate.is_absolute() else path.parent / candidate).resolve()
        if resolved.is_file() and resolved not in result:
            result.append(resolved)
    if not result and path.is_file():
        for resolved in sorted(path.parent.iterdir()):
            if resolved.is_file() and resolved.suffix.lower() in {".ttf", ".otf", ".ttc"}:
                result.append(resolved.resolve())
    return result


def _die(message: str, code: int = 2):
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def _refresh_artifact_tool_output_report(report_path: Path, output_path: Path) -> None:
    """Bind the strict authoring receipt to the post-processed final PPTX.

    Artifact Tool writes its receipt before the repository-owned OOXML font
    face and chart-gap passes.  Those passes are part of the formal output,
    so leaving the pre-postprocess digest in the receipt creates a false
    provenance chain even when the deck itself is valid.
    """
    if not report_path.is_file() or not output_path.is_file():
        _die("Artifact Tool output receipt cannot bind the final PPTX")
    digest = hashlib.sha256()
    with output_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("backend") != "@oai/artifact-tool":
        _die("Artifact Tool output receipt is invalid before final binding")
    output = report.get("output") if isinstance(report.get("output"), dict) else {}
    output.update({
        "path": str(output_path.resolve()),
        "sha256": digest.hexdigest(),
        "bytes": output_path.stat().st_size,
    })
    report["output"] = output
    report["final_output_binding"] = {
        "status": "bound",
        "postprocess_complete": True,
        "passes": ["ooxml-font-faces", "chart-blank-gap-repair"],
    }
    atomic_write_json(report_path, report)


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
        choices=("artifact-tool",),
        default="artifact-tool",
        help="formal authoring engine; only @oai/artifact-tool is supported",
    )
    parser.add_argument("--node", help="Node executable for --authoring-backend artifact-tool")
    parser.add_argument("--node-modules", help="bundled node_modules directory for --authoring-backend artifact-tool")
    parser.add_argument("--strict-input", action="store_true", help="reject implicit primitive types, unsupported alignments and out-of-slide geometry")
    parser.add_argument("--require-native-structure", action="store_true", help="require native panels/tables and forbid semantic full-slide frame pictures")
    parser.add_argument("--require-text-fit", action="store_true", help="block authoring unless every formal text slot fits at its target typography")
    parser.add_argument("--text-fit-report", help="E3 full-slot text-fit report; defaults next to output PPTX")
    parser.add_argument("--text-fit-e4-receipt", help="E4 receipt binding the E3 audit to the exact authored PPTX")
    parser.add_argument("--authoring-plan", help="AuthoringPlan used to resolve and bind native geometry after export"); parser.add_argument("--geometry-resolution", help="Precomputed geometry-primitive-resolution/v2 report")
    args = parser.parse_args()

    layout_path = Path(args.layout)
    if not layout_path.exists():
        _die(f"layout file not found: {layout_path}")
    deck = _promote_native_structures(_load_deck(layout_path))
    deck = _expand_components(deck)
    if args.strict_input:
        try: enforce_strict_reference_layout(layout_path, deck, Path(args.out).resolve(), font_dir=args.font_dir, font_manifest=args.font_manifest)
        except ValueError as exc: _die(str(exc))

    # Fixed-reference authoring uses PageGraph geometry as the authoritative
    # object-placement source before typography fitting.  This is deterministic
    # and generic: only matching stable object ids are projected; unmatched
    # nodes are left for the downstream fail-closed geometry audit.
    route_path = layout_path.resolve().parent / "route-decision.json"
    route = {}
    if route_path.is_file():
        try:
            route = json.loads(route_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            route = {}
    page_geometry_calibration = None
    if route.get("route") == "reference-reconstruction":
        page_graph_path = layout_path.resolve().parent / "page-graph.json"
        if not page_graph_path.is_file():
            _die(f"reference reconstruction requires PageGraph geometry: {page_graph_path}")
        try:
            page_graph = json.loads(page_graph_path.read_text(encoding="utf-8"))
            deck, page_geometry_calibration = apply_page_graph_geometry(deck, page_graph)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            _die(f"PageGraph geometry calibration failed: {type(exc).__name__}: {exc}")

    semantic_report = validate_semantic_layout(deck)
    if not semantic_report.get("valid", False):
        issue_codes = ", ".join(str(item.get("code")) for item in semantic_report.get("issues", []))
        _die(f"semantic layout preflight failed: {issue_codes}")
    deck["strict_input"] = bool(args.strict_input)
    deck["require_native_structure"] = bool(args.require_native_structure or (args.strict_input and deck.get("editable_object_policy") == "native-semantic-objects"))
    output_path = Path(args.out).resolve()
    geometry_resolution = prepare_geometry_resolution(args.authoring_plan, args.geometry_resolution)
    geometry_resolution_path = None
    if geometry_resolution is not None:
        geometry_resolution_path = write_resolution_report(output_path, geometry_resolution)
        binding_report = validate_artifact_tool_binding(deck, geometry_resolution)
        binding_report_path = output_path.with_name(f"{output_path.stem}.geometry-binding.json")
        binding_report_path.write_text(json.dumps(binding_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not binding_report.get("valid"):
            issue_codes = ", ".join(str(item.get("code")) for item in binding_report.get("issues", []))
            _die(f"geometry Artifact Tool binding preflight failed: {issue_codes}")
    if page_geometry_calibration is not None:
        calibration_report = output_path.with_name(f"{output_path.stem}.page-geometry-calibration.json")
        calibration_report.parent.mkdir(parents=True, exist_ok=True)
        calibration_report.write_text(json.dumps(page_geometry_calibration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.font_dir:
        deck["font_dir"] = str(Path(args.font_dir).resolve())
        # Bind the strict E3 measurement to a deterministic task-local font.
        # Artifact Tool still registers the complete font directory for
        # authoring; this single file is the shared measurement baseline.
        font_files = sorted(
            path for path in Path(args.font_dir).resolve().iterdir()
            if path.is_file() and path.suffix.lower() in {".ttf", ".otf", ".ttc"}
        )
        if font_files:
            preferred = next((path for path in font_files if "regular" in path.stem.lower()), font_files[0])
            deck["text_fit_font_file"] = str(preferred)

    effective_font_dir = str(Path(args.font_dir).resolve()) if args.font_dir else deck.get("font_dir")
    effective_font_manifest = str(Path(args.font_manifest).resolve()) if args.font_manifest else deck.get("font_manifest")
    preflight = validate_reference_preflight(
        layout_path,
        deck,
        embed_fonts=bool(args.embed_fonts),
        authoring_backend=args.authoring_backend,
        font_dir=effective_font_dir,
        font_manifest=effective_font_manifest,
    )
    if not preflight.get("valid", False):
        issue_codes = ", ".join(str(item.get("code")) for item in preflight.get("issues", []))
        _die(f"reference reconstruction preflight failed: {issue_codes}")

    require_text_fit = bool(args.require_text_fit or args.strict_input or args.authoring_backend == "artifact-tool")
    text_fit_report = Path(args.text_fit_report).resolve() if args.text_fit_report else output_path.with_name(f"{output_path.stem}.text-fit-e3.json")
    text_fit_e4 = Path(args.text_fit_e4_receipt).resolve() if args.text_fit_e4_receipt else output_path.with_name(f"{output_path.stem}.text-fit-e4.json")
    e3_report = run_text_fit_e3(deck, layout_path, text_fit_report, required=require_text_fit)
    if require_text_fit and not e3_report.get("gate_passed"):
        _die(text_fit_failure_message(e3_report))
    if args.authoring_backend == "artifact-tool":
        if args.embed_fonts:
            _die("--embed-fonts is only supported by the historical compatibility backend; use the Artifact Tool's registered fonts for strict authoring")
        builder = Path(__file__).with_name("artifact_tool_authoring.mjs").resolve()
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
                "--report", str(report_path), "--inspect", str(inspect_path), "--overwrite",
            ]
            if geometry_resolution_path:
                command.extend(["--geometry-resolution", str(geometry_resolution_path)])
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
            completed = subprocess.run(command, cwd=str(SCRIPT_DIR), capture_output=True, text=True, check=False)
            if completed.stdout:
                print(completed.stdout, end="")
            if completed.returncode != 0:
                if completed.stderr:
                    print(completed.stderr, file=sys.stderr, end="")
                _die(f"Artifact Tool strict authoring failed with exit code {completed.returncode}")
        postprocess_authoring_output(output_path, deck, geometry_resolution)
        chart_gap_report = output_path.with_name(f"{output_path.stem}.chart-blank-gap-repair.json")
        gap_result = repair_chart_blank_gaps(output_path, deck, chart_gap_report)
        if not gap_result.get("valid", False):
            _die("Artifact Tool chart blank-gap OOXML repair failed")
        _refresh_artifact_tool_output_report(report_path, output_path)
        e4 = write_text_fit_e4_receipt(text_fit_e4, output_path, e3_report, required=require_text_fit)
        if require_text_fit and e4 is None:
            _die("E4 text-fit receipt cannot bind missing authored PPTX")
        if require_text_fit and not e4.get("valid"):
            _die("E4 text-fit receipt blocked because E3 did not pass")
        return

    _die("formal authoring route did not complete through @oai/artifact-tool")


if __name__ == "__main__":
    main()
