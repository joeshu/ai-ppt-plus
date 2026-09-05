#!/usr/bin/env python3
"""Validate that final ImageGen assets are owned by the current rerun request."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA = "ai-ppt-plus/current-run-imagegen-validation/v1"


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def validate(manifest_path: Path, request_id: str) -> dict:
    issues: list[dict] = []
    manifest = load(manifest_path)
    manifest_request_id = manifest.get("request_id")
    if not manifest_request_id:
        issues.append({"code": "manifest_request_id_missing"})
    elif manifest_request_id != request_id:
        issues.append({"code": "manifest_request_id_mismatch", "expected": request_id, "actual": manifest_request_id})
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
    for index, asset in enumerate(assets, 1):
        if not isinstance(asset, dict):
            issues.append({"code": "asset_record_invalid", "index": index})
            continue
        asset_id = asset.get("id") or asset.get("node_id") or f"asset-{index}"
        asset_request_id = asset.get("request_id")
        if not asset_request_id:
            issues.append({"code": "asset_request_id_missing", "asset_id": asset_id})
        elif asset_request_id != request_id:
            issues.append({"code": "asset_request_id_mismatch", "asset_id": asset_id, "expected": request_id, "actual": asset_request_id})
    return {"schema": SCHEMA, "valid": not issues, "request_id": request_id, "manifest_request_id": manifest_request_id, "asset_count": len(assets), "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        report = validate(Path(args.manifest), args.request_id)
    except Exception as exc:
        report = {"schema": SCHEMA, "valid": False, "request_id": args.request_id, "issues": [{"code": "imagegen_manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"}]}
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
