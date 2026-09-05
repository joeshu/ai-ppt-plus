#!/usr/bin/env python3
"""Fail-closed preflight for direct reference-reconstruction authoring.

The normal ai-ppt-editable route runs through run_pipeline.py. This module
protects the lower-level composer as well, so a caller cannot bypass the
mandatory native-imagegen asset route or portable CJK font route merely by
calling compose_pptx.py directly.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from validate_imagegen_final_assets import validate as validate_final_imagegen_assets

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
MANDATORY_OBJECT_TYPES = {"extracted_icon", "editable_vector", "traceable_static_graphic"}
MANDATORY_ROLES = {
    "icon", "badge", "illustration", "decorative_art", "decorative-art",
    "decoration", "complex_art", "complex-art", "artistic_typography",
    "artistic-typography", "gradient_visual", "gradient-visual",
}
BRAND_ROLES = {"logo", "brand", "brand_lockup", "brand-lockup", "wordmark", "brand-logo"}


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _contains_cjk(value: object) -> bool:
    if isinstance(value, str):
        return bool(CJK_RE.search(value))
    if isinstance(value, dict):
        return any(_contains_cjk(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_cjk(child) for child in value)
    return False


def _objects_from_manifest(data: dict) -> list[dict]:
    objects: list[dict] = []
    for slide in data.get("slides") or []:
        if isinstance(slide, dict) and isinstance(slide.get("objects"), list):
            objects.extend(item for item in slide["objects"] if isinstance(item, dict))
    if isinstance(data.get("objects"), list):
        objects.extend(item for item in data["objects"] if isinstance(item, dict))
    return objects


def _requires_native_imagegen(objects: list[dict]) -> bool:
    for item in objects:
        role = str(item.get("role", "")).strip().lower().replace(" ", "_")
        object_type = str(item.get("object_type", item.get("type", ""))).strip().lower()
        if role in BRAND_ROLES:
            continue
        if object_type in MANDATORY_OBJECT_TYPES or role in MANDATORY_ROLES:
            return True
    return False


def validate_reference_preflight(
    layout_path: Path,
    deck: dict,
    *,
    embed_fonts: bool,
    font_dir: str | None = None,
    font_manifest: str | None = None,
) -> dict:
    root = layout_path.resolve().parent
    route_path = root / "route-decision.json"
    issues: list[dict] = []
    result = {
        "schema": "ai-ppt-plus/reference-compose-preflight/v1",
        "valid": True,
        "required": False,
        "route": None,
        "imagegen_required": False,
        "cjk_required": False,
        "issues": issues,
    }
    if not route_path.is_file():
        return result
    try:
        route = _load_json(route_path)
    except Exception as exc:
        issues.append({"code": "route_decision_unreadable", "message": f"{type(exc).__name__}: {exc}"})
        result["valid"] = False
        return result
    result["route"] = route.get("route")
    if route.get("route") != "reference-reconstruction":
        return result
    result["required"] = True

    object_manifest_path = root / "slide-object-manifest.json"
    if not object_manifest_path.is_file():
        issues.append({"code": "reference_object_manifest_missing", "path": str(object_manifest_path)})
        objects: list[dict] = []
    else:
        try:
            objects = _objects_from_manifest(_load_json(object_manifest_path))
        except Exception as exc:
            issues.append({"code": "reference_object_manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"})
            objects = []

    imagegen_required = _requires_native_imagegen(objects)
    result["imagegen_required"] = imagegen_required
    if imagegen_required:
        manifest_path = root / "imagegen-assets-manifest.json"
        if not manifest_path.is_file():
            issues.append({"code": "imagegen_final_asset_manifest_missing", "path": str(manifest_path)})
        else:
            try:
                imagegen_report = validate_final_imagegen_assets(manifest_path, strict=True)
            except Exception as exc:
                issues.append({"code": "imagegen_final_asset_manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"})
            else:
                if not imagegen_report.get("valid"):
                    issues.append({
                        "code": "imagegen_final_asset_gate_failed",
                        "errors": imagegen_report.get("errors", []),
                    })

    cjk_required = _contains_cjk(deck)
    result["cjk_required"] = cjk_required
    if cjk_required:
        if not embed_fonts:
            issues.append({"code": "reference_cjk_requires_embedded_fonts"})
        resolved_font_dir = font_dir or deck.get("font_dir")
        resolved_font_manifest = font_manifest or deck.get("font_manifest")
        if not resolved_font_dir and not resolved_font_manifest:
            issues.append({"code": "reference_cjk_font_evidence_missing"})

    result["valid"] = not issues
    return result
