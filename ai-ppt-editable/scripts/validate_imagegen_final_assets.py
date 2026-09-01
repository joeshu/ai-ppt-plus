#!/usr/bin/env python3
"""Enforce imagegen as the final route for visual asset classes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REQUIRED = {"icon", "icons", "badge", "gradient", "gradient_visual", "complex_art", "illustration", "artistic_typography", "decorative_art"}
BRAND = {"logo", "brand", "brand_lockup", "wordmark"}


def _class(item: dict) -> str:
    value = item.get("asset_class", item.get("category", item.get("role", "")))
    return str(value).strip().lower().replace("-", "_")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate(path: Path, *, strict: bool = False) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[dict] = []
    policy = data.get("provenance_policy")
    if strict and policy != "imagegen_final_assets":
        errors.append({"code": "wrong_provenance_policy", "observed": policy})
    assets = data.get("assets")
    if not isinstance(assets, list):
        errors.append({"code": "assets_not_list"})
        assets = []
    records = []
    for index, item in enumerate(assets, 1):
        if not isinstance(item, dict):
            errors.append({"code": "asset_not_object", "index": index})
            continue
        asset_id = item.get("asset_id") or item.get("id") or f"asset-{index}"
        cls = _class(item)
        if cls in BRAND:
            records.append({"asset_id": asset_id, "asset_class": cls, "route": "official-brand-exception"})
            continue
        if cls not in REQUIRED:
            records.append({"asset_id": asset_id, "asset_class": cls, "route": item.get("provenance_mode") or "unspecified"})
            continue
        route = str(item.get("provenance_mode", "")).lower()
        required = ("generated_source", "copied_to", "prompt_file", "backend")
        missing = [key for key in required if not item.get(key)]
        if route != "imagegen":
            errors.append({"code": "final_asset_not_imagegen", "asset_id": asset_id, "asset_class": cls, "observed": route})
        if missing:
            errors.append({"code": "imagegen_evidence_missing", "asset_id": asset_id, "missing": missing})
        if item.get("source_reuse") is True or item.get("extraction_method") in {"source_reuse", "exact_crop", "crop"}:
            errors.append({"code": "source_reuse_final_asset_forbidden", "asset_id": asset_id})
        if item.get("sprite_sheet") is True or "sheet" in str(item.get("copied_to", "")).lower():
            errors.append({"code": "sprite_sheet_not_independent_asset", "asset_id": asset_id})
        copied = Path(str(item.get("copied_to", "")))
        if copied.is_absolute() and copied.exists() and item.get("sha256") and _sha256(copied) != item.get("sha256"):
            errors.append({"code": "delivered_hash_mismatch", "asset_id": asset_id})
        records.append({"asset_id": asset_id, "asset_class": cls, "route": route, "generated_source": item.get("generated_source"), "copied_to": item.get("copied_to")})
    return {"schema": "ai-ppt-plus/imagegen-final-assets/v1", "valid": not errors, "strict": strict, "required_classes": sorted(REQUIRED), "asset_count": len(assets), "records": records, "errors": errors, "human_visual_review_required": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate(args.manifest.resolve(), strict=args.strict)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
