#!/usr/bin/env python3
"""Fail closed when source complex visuals lack independent ImageGen finals.

``imagegen-assets-manifest.json`` proves the assets it lists.  This validator
adds the missing upstream-to-final coverage proof: every complex visual in the
source inventory (and, when supplied, every visual PageGraph node) must map to
one independent native ImageGen final asset.  Source crops are evidence only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "ai-ppt-plus/source-visual-assets-validation/v1"
INVENTORY_SCHEMA = "ai-ppt-plus/source-visual-inventory/v1"
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
VISUAL_TYPES = {"icon", "illustration", "decoration", "image", "art", "badge", "logo", "brand", "wordmark"}
IMAGEGEN_ROLES = {
    "icon", "icons", "badge", "gradient", "gradient_visual", "complex_art",
    "complex-art", "illustration", "decorative_art", "decorative-art",
    "artistic_typography", "artistic-typography", "logo", "brand",
    "brand_lockup", "brand-lockup", "wordmark", "brand-logo",
    "calligraphic_slogan", "signature", "seal", "brand_band", "5g_mark",
    "locked_brand_art", "skyline", "ribbon",
}
BRAND_ROLES = {
    "logo", "brand", "brand_lockup", "brand-lockup", "wordmark", "brand-logo",
    "calligraphic_slogan", "signature", "seal", "brand_band", "5g_mark",
    "locked_brand_art",
}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(base: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value)
    return (candidate if candidate.is_absolute() else base / candidate).resolve()


def _role(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _bbox(value: object) -> bool:
    if not isinstance(value, list) or len(value) != 4:
        return False
    try:
        x, y, w, h = (float(item) for item in value)
    except (TypeError, ValueError):
        return False
    return x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= 1.000001 and y + h <= 1.000001


def _inventory_visuals(data: dict[str, Any], issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if data.get("schema") != INVENTORY_SCHEMA:
        issues.append({"severity": "blocker", "code": "source_visual_inventory_schema_invalid", "expected": INVENTORY_SCHEMA, "observed": data.get("schema")})
    source = data.get("source")
    if not isinstance(source, dict):
        issues.append({"severity": "blocker", "code": "source_visual_inventory_source_missing"})
    else:
        if not SHA256_RE.fullmatch(str(source.get("sha256", ""))):
            issues.append({"severity": "blocker", "code": "source_visual_inventory_source_sha_invalid"})
        for field in ("width_px", "height_px"):
            if not isinstance(source.get(field), int) or source.get(field, 0) <= 0:
                issues.append({"severity": "blocker", "code": "source_visual_inventory_dimensions_invalid", "field": field})

    visuals = data.get("visuals")
    if not isinstance(visuals, list):
        issues.append({"severity": "blocker", "code": "source_visual_inventory_visuals_missing"})
        return []
    seen: set[str] = set()
    valid: list[dict[str, Any]] = []
    for index, visual in enumerate(visuals, 1):
        if not isinstance(visual, dict):
            issues.append({"severity": "blocker", "code": "source_visual_inventory_visual_invalid", "index": index})
            continue
        visual_id = str(visual.get("visual_id") or "").strip()
        if not visual_id:
            issues.append({"severity": "blocker", "code": "source_visual_inventory_visual_id_missing", "index": index})
            continue
        if visual_id in seen:
            issues.append({"severity": "blocker", "code": "source_visual_inventory_visual_id_duplicate", "visual_id": visual_id})
        seen.add(visual_id)
        page = visual.get("page")
        if not isinstance(page, int) or page <= 0:
            issues.append({"severity": "blocker", "code": "source_visual_inventory_page_invalid", "visual_id": visual_id})
        if not isinstance(visual.get("semantic_role"), str) or not visual.get("semantic_role", "").strip():
            issues.append({"severity": "blocker", "code": "source_visual_inventory_role_missing", "visual_id": visual_id})
        if not _bbox(visual.get("bbox_norm")):
            issues.append({"severity": "blocker", "code": "source_visual_inventory_bbox_invalid", "visual_id": visual_id})
        route = str(visual.get("required_route") or "imagegen").strip().lower()
        if route != "imagegen":
            issues.append({"severity": "blocker", "code": "source_visual_inventory_route_invalid", "visual_id": visual_id, "required_route": route})
        asset_id = str(visual.get("asset_id") or "").strip()
        if not asset_id:
            issues.append({"severity": "blocker", "code": "source_visual_inventory_asset_id_missing", "visual_id": visual_id})
        valid.append({**visual, "visual_id": visual_id, "asset_id": asset_id, "required_route": route})
    return valid


def _page_graph_visuals(data: dict[str, Any], issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        issues.append({"severity": "blocker", "code": "page_graph_nodes_missing"})
        return []
    result: list[dict[str, Any]] = []
    for index, node in enumerate(nodes, 1):
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or node.get("object_id") or "").strip()
        node_type = _role(node.get("type"))
        role = _role(node.get("role"))
        if not node_id or (node_type not in VISUAL_TYPES and role not in IMAGEGEN_ROLES):
            continue
        result.append({"id": node_id, "type": node_type, "role": role, "bbox_norm": node.get("bbox"), "index": index})
    return result


def _layout_asset_ids(data: dict[str, Any], issues: list[dict[str, Any]]) -> set[str]:
    """Collect asset/object/file identities actually bound into the layout."""
    slides = data.get("slides")
    if not isinstance(slides, list):
        issues.append({"severity": "blocker", "code": "source_visual_layout_slides_missing"})
        return set()
    ids: set[str] = set()
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        for key in ("icons", "images", "assets", "visual_assets", "pictures"):
            items = slide.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                for field in ("asset_id", "object_id", "id"):
                    value = str(item.get(field) or "").strip()
                    if value:
                        ids.add(value)
                file_value = str(item.get("file") or item.get("path") or "").strip()
                if file_value:
                    ids.add(Path(file_value).stem)
    return ids


def _asset_id(asset: dict[str, Any]) -> str:
    return str(asset.get("asset_id") or asset.get("id") or "").strip()


def _asset_issues(asset: dict[str, Any], visual: dict[str, Any], manifest_root: Path, issues: list[dict[str, Any]]) -> None:
    asset_id = visual["asset_id"]
    route = str(asset.get("provenance_mode") or "").strip().lower()
    visual_role = _role(visual.get("semantic_role"))
    exact_brand = (visual_role in BRAND_ROLES and route == "provided_exact_brand_asset" and asset.get("extraction_method") == "approved-source-asset" and asset.get("exact_brand_asset") is True and asset.get("user_supplied") is True and asset.get("source_kind") in {"standalone_file", "official_asset"} and asset.get("independent_asset") is True and not asset.get("source_bbox") and asset.get("source_reuse") is not True)
    if route != "imagegen" and not exact_brand:
        issues.append({"severity": "blocker", "code": "source_visual_asset_requires_imagegen", "visual_id": visual["visual_id"], "asset_id": asset_id, "observed": route or None})
    if asset.get("independent_asset") is not True:
        issues.append({"severity": "blocker", "code": "source_visual_asset_not_independent", "visual_id": visual["visual_id"], "asset_id": asset_id})
    asset_class = _role(asset.get("asset_class") or asset.get("category") or asset.get("role"))
    if not asset_class:
        issues.append({"severity": "blocker", "code": "source_visual_asset_class_missing", "visual_id": visual["visual_id"], "asset_id": asset_id})
    if visual_role in BRAND_ROLES and asset_class and asset_class not in BRAND_ROLES:
        issues.append({"severity": "blocker", "code": "source_visual_brand_class_mismatch", "visual_id": visual["visual_id"], "asset_id": asset_id, "asset_class": asset_class})
    forbidden_crop = asset.get("source_reuse") is True or str(asset.get("extraction_method") or "").lower() in {"crop", "exact_crop", "source_reuse", "source-crop"}
    if forbidden_crop or route == "source_reuse":
        issues.append({"severity": "blocker", "code": "source_visual_asset_crop_fallback_forbidden", "visual_id": visual["visual_id"], "asset_id": asset_id})
    evidence_fields = ("source_ref", "copied_to", "source_sha256") if exact_brand else ("generated_source", "copied_to", "prompt_file", "backend")
    for field in evidence_fields:
        if not isinstance(asset.get(field), str) or not asset[field].strip():
            issues.append({"severity": "blocker", "code": "source_visual_asset_evidence_missing", "visual_id": visual["visual_id"], "asset_id": asset_id, "field": field})
    for field in (("source_ref",) if exact_brand else ("generated_source", "prompt_file")):
        evidence_path = _resolve(manifest_root, asset.get(field))
        if evidence_path is None or not evidence_path.is_file():
            issues.append({"severity": "blocker", "code": "source_visual_asset_evidence_file_missing", "visual_id": visual["visual_id"], "asset_id": asset_id, "field": field, "path": str(evidence_path) if evidence_path else None})
    if route == "imagegen" and "imagegen" not in str(asset.get("backend") or "").lower():
        issues.append({"severity": "blocker", "code": "source_visual_asset_non_imagegen_backend", "visual_id": visual["visual_id"], "asset_id": asset_id, "backend": asset.get("backend")})
    copied = _resolve(manifest_root, asset.get("copied_to"))
    if copied is None or not copied.is_file():
        issues.append({"severity": "blocker", "code": "source_visual_asset_final_file_missing", "visual_id": visual["visual_id"], "asset_id": asset_id, "path": str(copied) if copied else None})
    declared = asset.get("sha256") or (asset.get("source_sha256") if exact_brand else None)
    if not isinstance(declared, str) or not declared.strip():
        issues.append({"severity": "blocker", "code": "source_visual_asset_hash_missing", "visual_id": visual["visual_id"], "asset_id": asset_id})
    elif not SHA256_RE.fullmatch(declared):
        issues.append({"severity": "blocker", "code": "source_visual_asset_hash_invalid", "visual_id": visual["visual_id"], "asset_id": asset_id})
    elif copied is not None and copied.is_file():
        observed = _sha256(copied)
        if declared.lower() != observed:
            issues.append({"severity": "blocker", "code": "source_visual_asset_hash_mismatch", "visual_id": visual["visual_id"], "asset_id": asset_id, "declared": declared, "observed": observed})


def validate(inventory_path: Path, imagegen_manifest_path: Path | None = None, page_graph_path: Path | None = None, layout_path: Path | None = None) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    try:
        inventory = _load(inventory_path)
    except Exception as exc:
        return {"schema": SCHEMA, "valid": False, "status": "blocked", "visual_count": 0, "required_imagegen_count": 0, "covered_count": 0, "issues": [{"severity": "blocker", "code": "source_visual_inventory_unreadable", "message": f"{type(exc).__name__}: {exc}"}]}
    visuals = _inventory_visuals(inventory, issues)
    graph_visuals: list[dict[str, Any]] = []
    if page_graph_path is not None:
        try:
            graph_visuals = _page_graph_visuals(_load(page_graph_path), issues)
        except Exception as exc:
            issues.append({"severity": "blocker", "code": "page_graph_unreadable", "message": f"{type(exc).__name__}: {exc}"})
    elif not visuals:
        issues.append({"severity": "blocker", "code": "source_visual_inventory_empty_without_page_graph"})
    inventory_ids = {item["visual_id"] for item in visuals} | {item["asset_id"] for item in visuals if item.get("asset_id")}
    for node in graph_visuals:
        if node["id"] not in inventory_ids:
            issues.append({"severity": "blocker", "code": "source_visual_inventory_missing_graph_asset", "node_id": node["id"], "role": node["role"] or node["type"]})

    layout_asset_ids: set[str] = set()
    if layout_path is not None:
        try:
            layout_asset_ids = _layout_asset_ids(_load(layout_path), issues)
        except Exception as exc:
            issues.append({"severity": "blocker", "code": "source_visual_layout_unreadable", "message": f"{type(exc).__name__}: {exc}"})
        for visual in visuals:
            asset_id = str(visual.get("asset_id") or "").strip()
            if asset_id and asset_id not in layout_asset_ids:
                issues.append({"severity": "blocker", "code": "source_visual_asset_not_bound_to_layout", "visual_id": visual["visual_id"], "asset_id": asset_id})

    source_sha = ((inventory.get("source") or {}).get("sha256") if isinstance(inventory.get("source"), dict) else None)
    assets: dict[str, dict[str, Any]] = {}
    manifest = None
    if visuals:
        if imagegen_manifest_path is None or not imagegen_manifest_path.is_file():
            issues.append({"severity": "blocker", "code": "source_visual_imagegen_manifest_missing", "path": str(imagegen_manifest_path) if imagegen_manifest_path else None})
        else:
            try:
                manifest = _load(imagegen_manifest_path)
            except Exception as exc:
                issues.append({"severity": "blocker", "code": "source_visual_imagegen_manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"})
    if manifest is not None:
        manifest_sha = manifest.get("source_sha256")
        if source_sha and not isinstance(manifest_sha, str):
            issues.append({"severity": "blocker", "code": "source_visual_manifest_source_hash_missing"})
        elif source_sha and manifest_sha and str(source_sha).lower() != str(manifest_sha).lower():
            issues.append({"severity": "blocker", "code": "source_visual_source_hash_mismatch", "inventory": source_sha, "manifest": manifest_sha})
        raw_assets = manifest.get("assets")
        if not isinstance(raw_assets, list):
            issues.append({"severity": "blocker", "code": "source_visual_imagegen_assets_missing"})
            raw_assets = []
        for item in raw_assets:
            if isinstance(item, dict) and _asset_id(item):
                asset_id = _asset_id(item)
                if asset_id in assets:
                    issues.append({"severity": "blocker", "code": "source_visual_asset_id_duplicate_in_manifest", "asset_id": asset_id})
                assets[asset_id] = item

    covered = 0
    for visual in visuals:
        asset_id = visual.get("asset_id")
        asset = assets.get(asset_id) if asset_id else None
        if asset is None:
            issues.append({"severity": "blocker", "code": "source_visual_asset_coverage_missing", "visual_id": visual["visual_id"], "asset_id": asset_id})
            continue
        covered += 1
        if imagegen_manifest_path is not None:
            _asset_issues(asset, visual, imagegen_manifest_path.parent, issues)

    result = {
        "schema": SCHEMA,
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "inventory": str(inventory_path),
        "imagegen_manifest": str(imagegen_manifest_path) if imagegen_manifest_path else None,
        "page_graph": str(page_graph_path) if page_graph_path else None,
        "layout": str(layout_path) if layout_path else None,
        "visual_count": len(visuals),
        "required_imagegen_count": len(visuals),
        "covered_count": covered,
        "graph_visual_count": len(graph_visuals),
        "issues": issues,
        "human_visual_review_required": True,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--imagegen-manifest", type=Path)
    parser.add_argument("--page-graph", type=Path)
    parser.add_argument("--layout", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = validate(args.inventory.resolve(), args.imagegen_manifest.resolve() if args.imagegen_manifest else None, args.page_graph.resolve() if args.page_graph else None, args.layout.resolve() if args.layout else None)
    except Exception as exc:
        result = {"schema": SCHEMA, "valid": False, "status": "blocked", "visual_count": 0, "required_imagegen_count": 0, "covered_count": 0, "issues": [{"severity": "blocker", "code": "source_visual_assets_runtime_error", "message": f"{type(exc).__name__}: {exc}"}]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("valid") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
