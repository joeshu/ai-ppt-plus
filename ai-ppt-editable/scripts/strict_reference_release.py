#!/usr/bin/env python3
"""Strict reference reconstruction release gate.

This is the release entrypoint for fixed-reference image-to-editable work. It
runs the provenance-bound authoring transaction, renders the freshly authored
PPTX, compares the actual rendered canvas against the immutable source with the
repository strict visual thresholds, and emits object-region diagnostics.

A successful authoring operation is not a release pass. The deck is releasable
only after the fresh render passes the visual gate.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def run(command: list[str], label: str) -> None:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.returncode != 0:
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)
        raise SystemExit(f"{label} failed with exit code {completed.returncode}")


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def bbox(spec: dict, deck: dict) -> list[float] | None:
    raw = spec.get("bbox")
    if isinstance(raw, list) and len(raw) >= 4:
        x, y, w, h = map(float, raw[:4])
    else:
        try:
            x = float(spec.get("x", spec.get("left")))
            y = float(spec.get("y", spec.get("top")))
            w = float(spec.get("w", spec.get("width")))
            h = float(spec.get("h", spec.get("height")))
        except (TypeError, ValueError):
            return None
    if deck.get("units", "fraction") == "px":
        rw = float(deck.get("ref_width") or deck.get("reference_width") or deck.get("slide_width_px") or 1)
        rh = float(deck.get("ref_height") or deck.get("reference_height") or deck.get("slide_height_px") or 1)
        x, y, w, h = x / rw, y / rh, w / rw, h / rh
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > 1.001 or y + h > 1.001:
        return None
    return [round(x, 7), round(y, 7), round(w, 7), round(h, 7)]


def region_manifest(layout: Path, output: Path) -> dict:
    deck = load(layout)
    regions = []
    kinds = ("texts", "shapes", "tables", "charts", "images")
    for slide_no, slide in enumerate(deck.get("slides") or [], 1):
        for kind in kinds:
            for index, spec in enumerate(slide.get(kind) or [], 1):
                if not isinstance(spec, dict):
                    continue
                box = bbox(spec, deck)
                if box is None or box[2] * box[3] < 0.0005:
                    continue
                object_id = str(spec.get("object_id") or spec.get("name") or f"{kind}-{index}")
                regions.append({"region_id": f"s{slide_no}:{kind}:{object_id}", "role": "foreground", "weight": 1.0, "bbox": box})
    payload = {"schema": "ai-ppt-plus/auto-layout-regions/v1", "regions": regions}
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    parser.add_argument("--source", required=True)
    parser.add_argument("--layout", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--request-id")
    parser.add_argument("--font-dir")
    parser.add_argument("--font-manifest")
    parser.add_argument("--preview-dir")
    parser.add_argument("--authoring-backend", choices=("artifact-tool", "python-pptx"), default="artifact-tool")
    parser.add_argument("--node")
    parser.add_argument("--node-modules")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dpi", type=int, default=144)
    args = parser.parse_args()
    project = Path(args.project).resolve(); source = Path(args.source).resolve(); layout = Path(args.layout).resolve(); out = Path(args.out).resolve()
    command = [sys.executable, str(SCRIPT_DIR / "strict_reference_rerun.py"), str(project), "--source", str(source), "--layout", str(layout), "--out", str(out), "--authoring-backend", args.authoring_backend]
    for flag, value in (("--request-id", args.request_id), ("--font-dir", args.font_dir), ("--font-manifest", args.font_manifest), ("--preview-dir", args.preview_dir), ("--node", args.node), ("--node-modules", args.node_modules)):
        if value: command += [flag, value]
    if args.overwrite: command.append("--overwrite")
    run(command, "strict authoring transaction")
    current_path = project / "current-rerun.json"; current = load(current_path); run_dir = Path(current["authoring_provenance"]).resolve().parent
    render_dir = run_dir / "final-render"; render_report = run_dir / "final-render.json"
    render_cmd = [sys.executable, str(SCRIPT_DIR / "render_pptx.py"), str(out), "--output-dir", str(render_dir), "--dpi", str(args.dpi), "--report", str(render_report)]
    if args.font_dir: render_cmd += ["--font-dir", str(Path(args.font_dir).resolve())]
    run(render_cmd, "fresh PPTX render")
    rendered = render_dir / "slide-1.png"
    if not rendered.is_file(): raise SystemExit("fresh render did not produce slide-1.png")
    visual_report = run_dir / "strict-reference-visual.json"
    visual_cmd = [sys.executable, str(SCRIPT_DIR / "compare_visual.py"), str(rendered), str(source), "--raw-slide", "--strict", "--report", str(visual_report)]
    visual = subprocess.run(visual_cmd, text=True, capture_output=True, check=False)
    if visual.stdout: print(visual.stdout, end="")
    regions_path = run_dir / "auto-layout-regions.json"; region_manifest(layout, regions_path); region_report = run_dir / "auto-region-visual.json"
    region_run = subprocess.run([sys.executable, str(SCRIPT_DIR / "compare_visual_regions.py"), str(rendered), str(source), str(regions_path), "--report", str(region_report)], text=True, capture_output=True, check=False)
    if region_run.stdout: print(region_run.stdout, end="")
    current.update({"render": str(rendered), "render_report": str(render_report), "strict_reference_visual": str(visual_report), "auto_region_visual": str(region_report), "visual_gate_required": True, "visual_gate_passed": visual.returncode == 0, "status": "rendered-and-visual-gated" if visual.returncode == 0 else "blocked-by-rendered-reference-fidelity"})
    current_path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if visual.returncode != 0:
        if visual.stderr: print(visual.stderr, file=sys.stderr)
        raise SystemExit("fresh authored PPTX failed strict rendered reference fidelity; repair responsible layers and rerun")
    print(json.dumps({"status": "ok", "deck": str(out), "render": str(rendered), "visual_report": str(visual_report), "region_report": str(region_report)}, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
