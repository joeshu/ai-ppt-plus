#!/usr/bin/env python3
"""Verify approved ImageGen bytes are actually embedded in the delivered PPTX."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

SCHEMA = "ai-ppt-plus/embedded-imagegen-assets-validation/v1"
HASH_KEYS = ("actual_sha256", "sha256", "asset_sha256", "path_sha256", "copied_to_sha256")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _declared_hash(asset: dict) -> str | None:
    for key in HASH_KEYS:
        value = asset.get(key)
        if isinstance(value, str) and len(value) == 64:
            return value.lower()
    return None


def validate(pptx_path: Path, manifest_path: Path, request_id: str) -> dict:
    issues: list[dict] = []
    manifest = load(manifest_path)
    if manifest.get("request_id") != request_id:
        issues.append({"code": "manifest_request_id_mismatch", "expected": request_id, "actual": manifest.get("request_id")})
    if not pptx_path.is_file():
        issues.append({"code": "deck_missing", "path": str(pptx_path)})
        return {"schema": SCHEMA, "valid": False, "request_id": request_id, "issues": issues}

    media: list[dict] = []
    with zipfile.ZipFile(pptx_path, "r") as archive:
        for name in sorted(archive.namelist()):
            if name.startswith("ppt/media/") and not name.endswith("/"):
                data = archive.read(name)
                media.append({"part": name, "sha256": sha256_bytes(data), "bytes": len(data)})
    media_hashes = {row["sha256"] for row in media}

    approved: list[dict] = []
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
    for index, asset in enumerate(assets, 1):
        if not isinstance(asset, dict):
            continue
        asset_id = asset.get("id") or asset.get("node_id") or f"asset-{index}"
        if asset.get("request_id") != request_id:
            issues.append({"code": "asset_request_id_mismatch", "asset_id": asset_id, "expected": request_id, "actual": asset.get("request_id")})
            continue
        declared = _declared_hash(asset)
        path_value = asset.get("path") or asset.get("copied_to") or asset.get("asset_path")
        observed = None
        if isinstance(path_value, str):
            candidate = Path(path_value)
            if not candidate.is_absolute():
                candidate = (manifest_path.parent / candidate).resolve()
            if candidate.is_file():
                observed = sha256_file(candidate)
                if declared and observed != declared:
                    issues.append({"code": "approved_asset_source_hash_mismatch", "asset_id": asset_id, "declared": declared, "observed": observed})
                if not declared:
                    declared = observed
        if not declared:
            issues.append({"code": "approved_asset_hash_missing", "asset_id": asset_id})
            continue
        embedded_parts = [row["part"] for row in media if row["sha256"] == declared]
        approved.append({"asset_id": asset_id, "sha256": declared, "embedded_parts": embedded_parts})
        if not embedded_parts:
            issues.append({"code": "approved_asset_missing_from_pptx", "asset_id": asset_id, "sha256": declared})

    return {
        "schema": SCHEMA,
        "valid": not issues,
        "request_id": request_id,
        "deck": str(pptx_path),
        "deck_sha256": sha256_file(pptx_path),
        "media_count": len(media),
        "media": media,
        "approved_assets": approved,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pptx", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        report = validate(Path(args.pptx), Path(args.manifest), args.request_id)
    except Exception as exc:
        report = {"schema": SCHEMA, "valid": False, "request_id": args.request_id, "issues": [{"code": "embedded_asset_validation_unreadable", "message": f"{type(exc).__name__}: {exc}"}]}
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
