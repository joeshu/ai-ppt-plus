#!/usr/bin/env python3
"""Block strict authoring when text cannot render or icons are font glyphs."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
FONT_SUFFIXES = {".ttf", ".otf", ".ttc"}
CJK_PROBES = (0x4E2D, 0x56FD, 0x4E1A, 0x52A1)


def _contains_cjk(value: Any) -> bool:
    if isinstance(value, str):
        return bool(CJK_RE.search(value))
    if isinstance(value, dict):
        return any(_contains_cjk(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_cjk(child) for child in value)
    return False


def _font_has_cjk(path: Path) -> tuple[bool, list[str]]:
    """Require actual Chinese cmap coverage; fontconfig fallback is not proof."""
    try:
        from fontTools.ttLib import TTCollection, TTFont

        faces = []
        collection = None
        if path.suffix.lower() == ".ttc" or path.read_bytes()[:4] == b"ttcf":
            collection = TTCollection(str(path), lazy=True)
            faces = list(collection.fonts)
        else:
            faces = [TTFont(str(path), lazy=True)]
        found: set[int] = set()
        try:
            for face in faces:
                cmap = face.getBestCmap() or {}
                found.update(codepoint for codepoint in CJK_PROBES if codepoint in cmap)
        finally:
            for face in faces:
                face.close()
            if collection is not None:
                collection.close()
        return len(found) >= 2, [f"U+{codepoint:04X}" for codepoint in sorted(found)]
    except Exception:
        return False, []


def _manifest_paths(path: Path) -> list[Path]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    raw: list[str] = []
    if isinstance(value, dict):
        if isinstance(value.get("file"), str):
            raw.append(value["file"])
        for key in ("files", "fonts"):
            for item in value.get(key) or []:
                if isinstance(item, str):
                    raw.append(item)
                elif isinstance(item, dict):
                    candidate = item.get("file") or item.get("path") or item.get("target")
                    if isinstance(candidate, str):
                        raw.append(candidate)
    return [candidate.resolve() for item in raw if (candidate := (Path(item) if Path(item).is_absolute() else path.parent / item)).is_file()]


def _font_candidates(layout_path: Path, deck: dict, font_dir: str | None, font_manifest: str | None) -> list[Path]:
    root = layout_path.resolve().parent
    candidates: list[Path] = []
    raw_dir = font_dir or deck.get("font_dir")
    if raw_dir:
        directory = Path(raw_dir)
        directory = directory if directory.is_absolute() else root / directory
        if directory.is_dir():
            candidates.extend(path.resolve() for path in directory.iterdir() if path.is_file() and path.suffix.lower() in FONT_SUFFIXES)
    raw_manifest = font_manifest or deck.get("font_manifest")
    if raw_manifest:
        manifest = Path(raw_manifest)
        manifest = manifest if manifest.is_absolute() else root / manifest
        if manifest.is_file():
            candidates.extend(_manifest_paths(manifest.resolve()))
    return list(dict.fromkeys(candidates))


def _visible_text(spec: dict) -> str:
    if spec.get("text") is not None:
        return "".join(map(str, spec["text"])) if isinstance(spec["text"], list) else str(spec["text"])
    runs = spec.get("runs") or []
    return "".join(str(run.get("text") or run.get("run") or "") if isinstance(run, dict) else str(run) for run in runs)


def _symbol_only(value: str) -> bool:
    compact = "".join(value.split())
    if not compact or len(compact) > 6 or any(char.isalnum() or CJK_RE.match(char) for char in compact):
        return False
    return any(unicodedata.category(char) in {"So", "Sk", "Sm"} for char in compact)


def validate(layout_path: Path, deck: dict, *, font_dir: str | None = None, font_manifest: str | None = None) -> dict:
    issues: list[dict] = []
    candidates = _font_candidates(layout_path, deck, font_dir, font_manifest)
    coverage = []
    for path in candidates:
        valid, probes = _font_has_cjk(path)
        coverage.append({"path": str(path), "cjk_coverage_valid": valid, "matched_probes": probes})
    if _contains_cjk(deck) and not any(item["cjk_coverage_valid"] for item in coverage):
        issues.append({
            "severity": "blocker",
            "code": "strict_cjk_font_coverage_missing",
            "message": "strict authoring requires a real font file whose cmap covers Chinese glyphs; fontconfig substitution is not evidence",
        })
    symbol_icons = []
    for slide_no, slide in enumerate(deck.get("slides") or [], 1):
        for kind in ("texts", "shapes"):
            for index, spec in enumerate(slide.get(kind) or [], 1):
                if not isinstance(spec, dict) or spec.get("allow_symbol_glyph") is True:
                    continue
                value = _visible_text(spec)
                if _symbol_only(value):
                    symbol_icons.append({"slide": slide_no, "object_id": str(spec.get("object_id") or spec.get("name") or f"{kind}-{index}"), "text": value})
    if symbol_icons:
        issues.append({
            "severity": "blocker",
            "code": "strict_symbol_glyph_visual_forbidden",
            "message": "font glyphs are not stable production icons/arrows; use native geometry or independent assets",
            "objects": symbol_icons,
        })
    return {
        "schema": "ai-ppt-plus/strict-layout-preflight/v1",
        "valid": not issues,
        "cjk_required": _contains_cjk(deck),
        "font_candidates": coverage,
        "symbol_glyph_object_count": len(symbol_icons),
        "issues": issues,
    }


def enforce_reference(layout_path: Path, deck: dict, output_path: Path, *, font_dir: str | None = None, font_manifest: str | None = None) -> dict | None:
    route_path = layout_path.resolve().parent / "route-decision.json"
    route_name = None
    if route_path.is_file():
        try:
            route_name = json.loads(route_path.read_text(encoding="utf-8")).get("route")
        except (OSError, json.JSONDecodeError):
            route_name = None
    if route_name != "reference-reconstruction" and deck.get("reference_reconstruction") is not True:
        return None
    report = validate(layout_path, deck, font_dir=font_dir, font_manifest=font_manifest)
    report_path = output_path.with_name(f"{output_path.stem}.strict-layout-preflight.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not report.get("valid"):
        codes = ", ".join(str(item.get("code")) for item in report.get("issues", []))
        raise ValueError(f"strict layout preflight failed: {codes}")
    return report
