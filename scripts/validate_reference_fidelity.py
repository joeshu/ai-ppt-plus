#!/usr/bin/env python3
"""Validate native-imagegen routing and typography evidence for references."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/reference-fidelity/v1"
IMAGEGEN_CLASSES = {"icons", "illustration", "complex_art", "gradient_visual"}
ASSET_CLASSES = IMAGEGEN_CLASSES | {"brand_lockup"}
REQUIRED_IMAGEGEN = ("prompt_file", "backend", "key_color")


def add(items: list[dict], code: str, **extra) -> None:
    row = {"severity": "blocker", "code": code}
    row.update(extra)
    items.append(row)


def bbox(value) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return False
    try:
        values = [float(item) for item in value]
    except (TypeError, ValueError):
        return False
    return all(math.isfinite(item) and item >= 0 for item in values) and values[2] > 0 and values[3] > 0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def path_under(root: Path, value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()


def check_asset(root: Path, asset: dict, policy: dict, issues: list[dict], index: str, require_delivery: bool) -> None:
    asset_class = asset.get("asset_class")
    mode = asset.get("provenance_mode")
    route = asset.get("route")
    if asset_class not in ASSET_CLASSES:
        add(issues, "asset_class_invalid", asset=index, value=asset_class)
        return
    if not isinstance(asset.get("asset_id"), str) or not asset["asset_id"].strip():
        add(issues, "asset_id_missing", asset=index)
    for field in ("source_bbox", "target_bbox"):
        if field in asset and not bbox(asset[field]):
            add(issues, "bbox_invalid", asset=index, field=field)
    if policy.get("asset_generation_required") and asset_class in IMAGEGEN_CLASSES:
        if mode != "imagegen" or route != "B4":
            add(issues, "native_imagegen_required", asset=index, asset_class=asset_class, route=route, provenance_mode=mode)
    if asset_class == "brand_lockup" and mode != "source_reuse":
        add(issues, "brand_lockup_must_be_reused", asset=index)
    if mode == "imagegen":
        for field in REQUIRED_IMAGEGEN:
            if not isinstance(asset.get(field), str) or not asset[field].strip():
                add(issues, "imagegen_evidence_missing", asset=index, field=field)
        if asset.get("no_text") is not True:
            add(issues, "generated_asset_must_be_text_free", asset=index)
        if asset.get("no_logo") is not True:
            add(issues, "generated_asset_must_be_logo_free", asset=index)
        if require_delivery:
            for field in ("generated_source", "copied_to"):
                value = asset.get(field)
                if not isinstance(value, str) or not value.strip():
                    add(issues, "delivered_asset_path_missing", asset=index, field=field)
                    continue
                asset_path = path_under(root, value)
                if not asset_path.is_file():
                    add(issues, "delivered_asset_missing", asset=index, field=field, path=str(asset_path))
            prompt_path = path_under(root, asset["prompt_file"])
            if not prompt_path.is_file():
                add(issues, "prompt_file_missing", asset=index, path=str(prompt_path))
            copied = asset.get("copied_to")
            if isinstance(copied, str) and copied:
                copied_path = path_under(root, copied)
                declared = asset.get("sha256")
                if copied_path.is_file() and isinstance(declared, str) and declared != sha256(copied_path):
                    add(issues, "copied_asset_hash_mismatch", asset=index, declared=declared, observed=sha256(copied_path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--require-delivery", action="store_true", help="also require generated/copied files and prompt files")
    parser.add_argument("--report")
    args = parser.parse_args()
    manifest = Path(args.manifest).resolve()
    issues: list[dict] = []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/reference-fidelity-validation/v1", "valid": False, "status": "blocked", "issues":[{"severity":"blocker","code":"manifest_unreadable","message":f"{type(exc).__name__}: {exc}"}]}
        if args.report:
            atomic_write_json(Path(args.report).resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 2
    if not isinstance(data, dict):
        add(issues, "manifest_not_object")
        data = {}
    if data.get("schema") != SCHEMA:
        add(issues, "schema_invalid", expected=SCHEMA, observed=data.get("schema"))
    policy = data.get("reference_policy")
    if not isinstance(policy, dict):
        add(issues, "reference_policy_missing")
        policy = {}
    classes = policy.get("required_asset_classes", [])
    if not isinstance(classes, list) or any(item not in IMAGEGEN_CLASSES for item in classes):
        add(issues, "required_asset_classes_invalid", value=classes)
    if policy.get("formal_text_policy") != "native_text_only":
        add(issues, "formal_text_must_be_native", value=policy.get("formal_text_policy"))
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        add(issues, "pages_missing_or_empty")
        pages = []
    seen_pages: set[str] = set()
    asset_count = 0
    for page_index, page in enumerate(pages):
        if not isinstance(page, dict):
            add(issues, "page_not_object", page_index=page_index)
            continue
        page_id = page.get("page_id") or f"page-{page_index + 1}"
        if page_id in seen_pages:
            add(issues, "duplicate_page_id", page_id=page_id)
        seen_pages.add(page_id)
        if not isinstance(page.get("reference_image"), str) or not page["reference_image"].strip():
            add(issues, "reference_image_missing", page_id=page_id)
        assets = page.get("assets")
        if not isinstance(assets, list) or not assets:
            add(issues, "page_assets_missing", page_id=page_id)
            assets = []
        for asset_index, asset in enumerate(assets):
            if not isinstance(asset, dict):
                add(issues, "asset_not_object", page_id=page_id, asset_index=asset_index)
                continue
            asset_count += 1
            check_asset(manifest.parent, asset, policy, issues, f"{page_id}:{asset_index}", args.require_delivery)
        observed_classes = {asset.get("asset_class") for asset in assets if isinstance(asset, dict)}
        for required in classes:
            if required not in observed_classes:
                add(issues, "required_asset_class_missing", page_id=page_id, asset_class=required)
        typography = page.get("typography")
        if not isinstance(typography, dict):
            add(issues, "typography_calibration_missing", page_id=page_id)
        else:
            roles = typography.get("required_roles")
            if not isinstance(roles, list) or not roles:
                add(issues, "typography_roles_missing", page_id=page_id)
            if typography.get("calibration_manifest") in (None, ""):
                add(issues, "typography_manifest_missing", page_id=page_id)
    result = {"schema":"ai-ppt-plus/reference-fidelity-validation/v1", "valid":not issues, "status":"passed" if not issues else "blocked", "manifest":str(manifest), "page_count":len(pages), "asset_count":asset_count, "issues":issues, "human_visual_review_required":True}
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
