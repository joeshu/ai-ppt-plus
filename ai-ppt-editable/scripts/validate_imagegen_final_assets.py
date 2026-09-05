#!/usr/bin/env python3
"""Enforce native imagegen as the final route for visual asset classes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

REQUIRED = {"icon", "icons", "badge", "gradient", "gradient_visual", "complex_art", "illustration", "artistic_typography", "decorative_art"}
BRAND = {"logo", "brand", "brand_lockup", "wordmark"}
IMAGEGEN_WORD = re.compile(r"(^|[-_.:/ ])imagegen($|[-_.:/ ])", re.I)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _class(item: dict) -> str:
    value = item.get("asset_class", item.get("category", item.get("role", "")))
    return str(value).strip().lower().replace("-", "_")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve(manifest: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value)
    return (candidate if candidate.is_absolute() else manifest.parent / candidate).resolve()


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
        approved_fallback = route == "source_reuse" and item.get("fallback_decision") == "user_approved" and item.get("decision_id") and item.get("decision_reason") and item.get("decision_timestamp")
        if route != "imagegen" and not approved_fallback:
            errors.append({"code": "final_asset_not_imagegen", "asset_id": asset_id, "asset_class": cls, "observed": route})
        if missing and not approved_fallback:
            errors.append({"code": "imagegen_evidence_missing", "asset_id": asset_id, "missing": missing})
        if (item.get("source_reuse") is True or item.get("extraction_method") in {"source_reuse", "exact_crop", "crop"}) and not approved_fallback:
            errors.append({"code": "source_reuse_final_asset_forbidden", "asset_id": asset_id})
        if approved_fallback and not (item.get("source_ref") and item.get("source_bbox") and item.get("source_sha256")):
            errors.append({"code": "approved_fallback_missing_source_evidence", "asset_id": asset_id})
        if item.get("sprite_sheet") is True or "sheet" in str(item.get("copied_to", "")).lower():
            errors.append({"code": "sprite_sheet_not_independent_asset", "asset_id": asset_id})

        if route == "imagegen":
            backend = str(item.get("backend", ""))
            if strict and not IMAGEGEN_WORD.search(backend):
                errors.append({"code": "non_native_imagegen_backend", "asset_id": asset_id, "backend": backend})
            for field in ("generated_source", "copied_to", "prompt_file"):
                resolved = _resolve(path, item.get(field))
                if strict and (resolved is None or not resolved.is_file()):
                    errors.append({"code": "imagegen_evidence_file_missing", "asset_id": asset_id, "field": field, "path": str(resolved) if resolved else None})
            copied = _resolve(path, item.get("copied_to"))
            declared_hash = item.get("sha256") or item.get("asset_sha256") or item.get("copied_to_sha256")
            if strict and (not isinstance(declared_hash, str) or not SHA256_RE.fullmatch(declared_hash)):
                errors.append({"code": "delivered_hash_missing_or_invalid", "asset_id": asset_id, "declared": declared_hash})
            elif copied is not None and copied.is_file() and declared_hash and _sha256(copied) != declared_hash:
                errors.append({"code": "delivered_hash_mismatch", "asset_id": asset_id})

        if approved_fallback:
            source = _resolve(path, item.get("source_ref"))
            if strict and (source is None or not source.is_file()):
                errors.append({"code": "approved_fallback_source_missing", "asset_id": asset_id, "path": str(source) if source else None})
            declared_source_hash = item.get("source_sha256")
            if strict and (not isinstance(declared_source_hash, str) or not SHA256_RE.fullmatch(declared_source_hash)):
                errors.append({"code": "approved_fallback_source_hash_invalid", "asset_id": asset_id, "declared": declared_source_hash})
            elif source is not None and source.is_file() and declared_source_hash and _sha256(source) != declared_source_hash:
                errors.append({"code": "approved_fallback_source_hash_mismatch", "asset_id": asset_id})

        records.append({"asset_id": asset_id, "asset_class": cls, "route": route, "generated_source": item.get("generated_source"), "copied_to": item.get("copied_to")})
    return {"schema": "ai-ppt-plus/imagegen-final-assets/v2", "valid": not errors, "strict": strict, "required_classes": sorted(REQUIRED), "asset_count": len(assets), "records": records, "errors": errors, "human_visual_review_required": True}


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
