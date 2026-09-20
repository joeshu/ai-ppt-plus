#!/usr/bin/env python3
"""Enforce brand/logo coverage from PageGraph into final generated assets.

Brand uses the native ImageGen final-asset route. Complete lockups must remain
a single independent generated asset so a logo mark and its wordmark cannot be
silently re-typeset as unrelated native text.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

BRAND_ROLES = {"logo", "brand", "brand_lockup", "brand-lockup", "wordmark", "brand-logo", "locked_brand_art"}
LOCKUP_ROLES = {"brand_lockup", "brand-lockup", "wordmark"}


def norm(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def validate_brand_coverage(run_root: Path) -> dict:
    page_graph = run_root / "page-graph.json"
    manifest = run_root / "imagegen-assets-manifest.json"
    result = {"schema": "ai-ppt-plus/brand-asset-coverage/v1", "valid": True, "required": False, "brand_ids": [], "issues": []}
    if not page_graph.is_file():
        return result
    graph = load(page_graph)
    brand_nodes = []
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        role = norm(node.get("role"))
        node_type = norm(node.get("type"))
        if role in BRAND_ROLES or node_type in {"logo", "brand", "wordmark"}:
            node_id = str(node.get("id") or "").strip()
            if not node_id:
                result["issues"].append({"severity": "blocker", "code": "brand_node_missing_id"})
                continue
            brand_nodes.append({"id": node_id, "role": role or node_type})
    if not brand_nodes:
        result["valid"] = not result["issues"]
        return result
    result["required"] = True
    result["brand_ids"] = [item["id"] for item in brand_nodes]
    if not manifest.is_file():
        result["issues"].append({"severity": "blocker", "code": "brand_imagegen_manifest_missing", "path": str(manifest)})
        result["valid"] = False
        return result
    data = load(manifest)
    assets = {str(item.get("asset_id") or item.get("id")): item for item in (data.get("assets") or []) if isinstance(item, dict) and (item.get("asset_id") or item.get("id"))}
    for node in brand_nodes:
        asset = assets.get(node["id"])
        if asset is None:
            result["issues"].append({"severity": "blocker", "code": "brand_asset_coverage_missing", "asset_id": node["id"], "role": node["role"]})
            continue
        if asset.get("independent_asset") is not True:
            result["issues"].append({"severity": "blocker", "code": "brand_asset_not_independent", "asset_id": node["id"]})
        if str(asset.get("provenance_mode") or "").lower() != "imagegen":
            result["issues"].append({"severity": "blocker", "code": "brand_asset_requires_native_imagegen", "asset_id": node["id"], "observed": asset.get("provenance_mode")})
        for field in ("generated_source", "copied_to", "prompt_file", "backend"):
            if not isinstance(asset.get(field), str) or not asset[field].strip():
                result["issues"].append({"severity": "blocker", "code": "brand_imagegen_evidence_missing", "asset_id": node["id"], "field": field})
        if "imagegen" not in str(asset.get("backend") or "").lower():
            result["issues"].append({"severity": "blocker", "code": "brand_non_imagegen_backend", "asset_id": node["id"], "backend": asset.get("backend")})
        if node["role"] in LOCKUP_ROLES:
            if asset.get("whole_asset_contract") is not True:
                result["issues"].append({"severity": "blocker", "code": "brand_lockup_whole_asset_contract_missing", "asset_id": node["id"]})
            if norm(asset.get("split_status")) in {"split", "grid_split", "component_split"}:
                result["issues"].append({"severity": "blocker", "code": "brand_lockup_illegally_split", "asset_id": node["id"]})
    result["valid"] = not result["issues"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = validate_brand_coverage(args.run_root.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
