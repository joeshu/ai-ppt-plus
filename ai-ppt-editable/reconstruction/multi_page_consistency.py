"""Cross-slide consistency checks for reconstructed editable decks."""
from __future__ import annotations

from collections import defaultdict
from math import isfinite
from typing import Any


def _id(item: dict[str, Any]) -> str:
    return str(item.get("object_id") or item.get("id") or item.get("name") or "")


def _size(item: dict[str, Any]) -> float | None:
    value = item.get("size", item.get("font_size"))
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and number > 0 else None


def audit_multi_page_consistency(deck: dict[str, Any], *, position_tolerance: float = .008, size_tolerance_pt: float = 1.0) -> dict[str, Any]:
    slides = deck.get("slides") or []
    if not isinstance(slides, list):
        raise ValueError("deck slides must be a list")
    rules = deck.get("consistency_rules") or {}
    locked_roles = set(rules.get("locked_roles") or ["title", "footer", "logo"])
    repeated_asset_roles = set(rules.get("repeated_asset_roles") or ["logo"])
    issues: list[dict[str, Any]] = []

    role_texts: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    role_assets: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for slide_no, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            continue
        for item in slide.get("texts", []) or []:
            if isinstance(item, dict) and item.get("role") in locked_roles:
                role_texts[str(item["role"])].append((slide_no, item))
        for collection in ("icons", "panels"):
            for item in slide.get(collection, []) or []:
                if isinstance(item, dict) and item.get("role") in repeated_asset_roles:
                    role_assets[str(item["role"])].append((slide_no, item))

    for role, entries in role_texts.items():
        if len(entries) < 2:
            continue
        base_slide, base = entries[0]
        base_size = _size(base)
        base_font = str(base.get("font") or deck.get("theme", {}).get("font") or "")
        base_xy = (float(base.get("x", 0)), float(base.get("y", 0)))
        for slide_no, item in entries[1:]:
            current_size = _size(item)
            current_font = str(item.get("font") or deck.get("theme", {}).get("font") or "")
            if base_size is not None and current_size is not None and abs(current_size - base_size) > size_tolerance_pt:
                issues.append({"kind": "text-size", "role": role, "slide": slide_no, "base_slide": base_slide, "base": base_size, "current": current_size})
            if base_font and current_font and current_font != base_font:
                issues.append({"kind": "text-font", "role": role, "slide": slide_no, "base_slide": base_slide, "base": base_font, "current": current_font})
            current_xy = (float(item.get("x", 0)), float(item.get("y", 0)))
            if max(abs(current_xy[0] - base_xy[0]), abs(current_xy[1] - base_xy[1])) > position_tolerance:
                issues.append({"kind": "text-position", "role": role, "slide": slide_no, "base_slide": base_slide, "base": list(base_xy), "current": list(current_xy)})

    for role, entries in role_assets.items():
        if len(entries) < 2:
            continue
        base_slide, base = entries[0]
        base_source = str(base.get("source_sha256") or base.get("file") or "")
        base_box = tuple(float(base.get(key, 0)) for key in ("x", "y", "w", "h"))
        for slide_no, item in entries[1:]:
            current_source = str(item.get("source_sha256") or item.get("file") or "")
            if base_source and current_source and current_source != base_source:
                issues.append({"kind": "asset-source", "role": role, "slide": slide_no, "base_slide": base_slide, "base": base_source, "current": current_source})
            current_box = tuple(float(item.get(key, 0)) for key in ("x", "y", "w", "h"))
            if max(abs(a - b) for a, b in zip(base_box, current_box)) > position_tolerance:
                issues.append({"kind": "asset-position", "role": role, "slide": slide_no, "base_slide": base_slide, "base": list(base_box), "current": list(current_box)})

    return {
        "schema": "ai-ppt-plus/multi-page-consistency/v1",
        "valid": not issues,
        "slide_count": len(slides),
        "locked_roles": sorted(locked_roles),
        "repeated_asset_roles": sorted(repeated_asset_roles),
        "issue_count": len(issues),
        "issues": issues,
    }
