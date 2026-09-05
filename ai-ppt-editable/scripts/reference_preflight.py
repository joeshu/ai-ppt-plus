#!/usr/bin/env python3
"""Fail-closed preflight for direct reference-reconstruction authoring.

Image-generation requirements are derived from the visual decomposition
(PageGraph), not from whether the user supplied separate icon files and not from
a downstream manifest self-declaration. The slide-object manifest is only a
cross-check of the already-understood visual inventory.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from validate_imagegen_final_assets import validate as validate_final_imagegen_assets

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
MANDATORY_GRAPH_TYPES = {"icon", "illustration", "decoration"}
MANDATORY_ROLES = {
    "icon", "badge", "illustration", "decorative_art", "decorative-art",
    "decoration", "complex_art", "complex-art", "artistic_typography",
    "artistic-typography", "gradient_visual", "gradient-visual",
}
BRAND_ROLES = {"logo", "brand", "brand_lockup", "brand-lockup", "wordmark", "brand-logo"}
FONT_SUFFIXES = {".ttf", ".otf", ".ttc", ".woff", ".woff2"}


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


def _norm_role(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _page_graph_assets(data: dict) -> list[dict]:
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("page-graph.json must contain nodes[]")
    assets: list[dict] = []
    for item in nodes:
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("id", "")).strip()
        node_type = str(item.get("type", "")).strip().lower()
        role = _norm_role(item.get("role"))
        if role in BRAND_ROLES:
            continue
        if node_type in MANDATORY_GRAPH_TYPES or role in MANDATORY_ROLES:
            if not node_id:
                raise ValueError("visual asset node is missing id")
            assets.append({"id": node_id, "type": node_type, "role": role})
    return assets


def _object_ids(data: dict) -> set[str]:
    result: set[str] = set()
    objects: list[dict] = []
    for slide in data.get("slides") or []:
        if isinstance(slide, dict) and isinstance(slide.get("objects"), list):
            objects.extend(item for item in slide["objects"] if isinstance(item, dict))
    if isinstance(data.get("objects"), list):
        objects.extend(item for item in data["objects"] if isinstance(item, dict))
    for item in objects:
        value = item.get("object_id") or item.get("id") or item.get("name")
        if value:
            result.add(str(value))
    return result


def _resolve(root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value)
    return (candidate if candidate.is_absolute() else root / candidate).resolve()


def _font_evidence(root: Path, font_dir: object, font_manifest: object) -> tuple[bool, dict]:
    resolved_dir = _resolve(root, font_dir)
    resolved_manifest = _resolve(root, font_manifest)
    details = {
        "font_dir": str(resolved_dir) if resolved_dir else None,
        "font_manifest": str(resolved_manifest) if resolved_manifest else None,
        "font_files": [],
    }
    if resolved_manifest is not None and resolved_manifest.is_file():
        try:
            manifest = _load_json(resolved_manifest)
        except Exception:
            manifest = None
        if isinstance(manifest, dict):
            details["manifest_readable"] = True
            return True, details
    if resolved_dir is not None and resolved_dir.is_dir():
        font_files = sorted(
            str(path) for path in resolved_dir.iterdir()
            if path.is_file() and path.suffix.lower() in FONT_SUFFIXES
        )
        details["font_files"] = font_files
        if font_files:
            return True, details
    return False, details


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
        "schema": "ai-ppt-plus/reference-compose-preflight/v3",
        "valid": True,
        "required": False,
        "route": None,
        "visual_inventory_source": None,
        "visual_asset_ids": [],
        "imagegen_required": False,
        "cjk_required": False,
        "font_evidence": None,
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

    # Primary authority: Astra/PageGraph visual decomposition of the full reference page.
    graph_path = root / "page-graph.json"
    graph_assets: list[dict] = []
    if not graph_path.is_file():
        issues.append({"code": "reference_page_graph_missing", "path": str(graph_path)})
    else:
        try:
            graph = _load_json(graph_path)
            graph_assets = _page_graph_assets(graph)
            result["visual_inventory_source"] = str(graph_path)
            result["visual_asset_ids"] = [item["id"] for item in graph_assets]
        except Exception as exc:
            issues.append({"code": "reference_page_graph_unreadable", "message": f"{type(exc).__name__}: {exc}"})

    # Secondary evidence only: downstream manifest must not omit visual assets understood upstream.
    object_manifest_path = root / "slide-object-manifest.json"
    manifest_ids: set[str] = set()
    if not object_manifest_path.is_file():
        issues.append({"code": "reference_object_manifest_missing", "path": str(object_manifest_path)})
    else:
        try:
            manifest_ids = _object_ids(_load_json(object_manifest_path))
        except Exception as exc:
            issues.append({"code": "reference_object_manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"})
    missing_from_manifest = sorted({item["id"] for item in graph_assets} - manifest_ids)
    if missing_from_manifest:
        issues.append({"code": "visual_asset_inventory_mismatch", "missing_object_ids": missing_from_manifest})

    imagegen_required = bool(graph_assets)
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
                    issues.append({"code": "imagegen_final_asset_gate_failed", "errors": imagegen_report.get("errors", [])})
                generated_ids = {str(item.get("asset_id")) for item in imagegen_report.get("records", []) if item.get("asset_id")}
                missing_generated = sorted({item["id"] for item in graph_assets} - generated_ids)
                if missing_generated:
                    issues.append({"code": "imagegen_asset_coverage_missing", "missing_asset_ids": missing_generated})

    cjk_required = _contains_cjk(deck)
    result["cjk_required"] = cjk_required
    if cjk_required:
        if not embed_fonts:
            issues.append({"code": "reference_cjk_requires_embedded_fonts"})
        resolved_font_dir = font_dir or deck.get("font_dir")
        resolved_font_manifest = font_manifest or deck.get("font_manifest")
        evidence_ok, evidence = _font_evidence(root, resolved_font_dir, resolved_font_manifest)
        result["font_evidence"] = evidence
        if not evidence_ok:
            issues.append({"code": "reference_cjk_font_evidence_missing", **evidence})

    result["valid"] = not issues
    return result
