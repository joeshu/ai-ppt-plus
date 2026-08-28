#!/usr/bin/env python3
"""Audit editable text against the text-style reconstruction contract.

This is intentionally deterministic: visual extraction remains a GPT/image
review step, while this tool catches the data-layer failures that made rich
text disappear during composition (plain text replacing runs, broken run
concatenation, visible Markdown markers, missing source boxes, and missing
style fields for emphasized content).

Usage:
    python3 scripts/validate_text_style_map.py layout.json
    python3 scripts/validate_text_style_map.py layout.json --strict --require-source-bbox
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from atomic_output import atomic_write_json

SLIDE_KEYS = {"background", "frame", "shapes", "icons", "texts"}
# Do not encode one source deck's Chinese labels here.  Model-specific or
# source-specific emphasis is declared as ``emphasis_expected`` in the layout;
# this regex only catches broadly observable numeric/redaction candidates.
EMPHASIS_RE = re.compile(r"(\d+(?:\.\d+)?%?|\d+元|[¥￥]\s*\d+|\*\*)")


def die(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(2)


def content(item: dict) -> str:
    if item.get("runs"):
        return "".join(str(r.get("text", "")) for r in item["runs"])
    return str(item.get("text", ""))


def has_style(run: dict) -> bool:
    return any(k in run for k in ("color", "bold", "italic", "size", "size_px", "size_ratio", "size_pct", "font"))


def audit(data: dict, require_bbox: bool) -> dict:
    if "slides" not in data:
        slide = {k: data[k] for k in SLIDE_KEYS if k in data}
        data = {"slides": [slide], **{k: v for k, v in data.items() if k not in SLIDE_KEYS}}

    errors: list[str] = []
    warnings: list[str] = []
    text_count = 0
    rich_count = 0
    emphasis_candidates = 0
    emphasis_with_runs = 0

    for si, slide in enumerate(data.get("slides", []), 1):
        for ti, item in enumerate(slide.get("texts", []), 1):
            text_count += 1
            label = item.get("name") or f"texts[{ti}]"
            txt = content(item)
            if not txt.strip():
                warnings.append(f"slide {si} {label}: empty text")
                continue
            literal_redaction = bool(item.get("literal_redaction")) or any(
                bool(r.get("literal_redaction")) for r in (item.get("runs") or []) if isinstance(r, dict)
            )
            if "**" in txt and not literal_redaction:
                errors.append(f"slide {si} {label}: visible Markdown marker '**' remains in text")
            if require_bbox and not isinstance(item.get("source_bbox"), list):
                warnings.append(f"slide {si} {label}: missing source_bbox")

            candidate = bool(item.get("emphasis_expected")) or bool(EMPHASIS_RE.search(txt))
            if candidate:
                emphasis_candidates += 1
            runs = item.get("runs")
            if runs:
                rich_count += 1
                if not isinstance(runs, list) or not runs:
                    errors.append(f"slide {si} {label}: runs must be a non-empty list")
                    continue
                if any(not isinstance(r, dict) for r in runs):
                    errors.append(f"slide {si} {label}: every run must be an object")
                if any("text" not in r for r in runs):
                    errors.append(f"slide {si} {label}: every run must contain text")
                if "text" in item and str(item["text"]) != txt:
                    errors.append(f"slide {si} {label}: text does not equal concatenated runs")
                if candidate:
                    emphasis_with_runs += 1
                    if not any(has_style(r) for r in runs):
                        warnings.append(f"slide {si} {label}: emphasis candidate has runs but no style overrides")
            elif candidate:
                warnings.append(f"slide {si} {label}: emphasis candidate is plain text; inspect for lost rich styling")

    return {
        "schema": "ai-ppt-plus/text-style-map-validation/v1",
        "valid": not errors,
        "text_count": text_count,
        "rich_text_count": rich_count,
        "emphasis_candidates": emphasis_candidates,
        "emphasis_with_runs": emphasis_with_runs,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("layout")
    ap.add_argument("--strict", action="store_true", help="Fail on warnings as well as errors.")
    ap.add_argument("--require-source-bbox", action="store_true")
    ap.add_argument("--report", help="Write JSON report to this path.")
    args = ap.parse_args()
    path = Path(args.layout)
    if not path.exists():
        die(f"layout not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        die(f"invalid JSON: {exc}")
    result = audit(data, args.require_source_bbox)
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    if result["errors"] or (args.strict and result["warnings"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
