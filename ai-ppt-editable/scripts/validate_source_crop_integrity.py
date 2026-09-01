#!/usr/bin/env python3
"""Verify that source_reuse assets came from their declared pixel bbox.

This is a post-baseline adapter. The frozen provenance validator checks file
and source hashes; this gate additionally checks the relationship between the
source bbox and the delivered pixels, which catches a neighboring crop with
otherwise consistent metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from atomic_output import atomic_write_json

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


POLICIES = {"exact", "derived"}


def add(issues: list[dict], code: str, **extra) -> None:
    row = {"severity": "blocker", "code": code}
    row.update(extra)
    issues.append(row)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pixel_digest(path: Path, bbox: list[float] | None = None) -> tuple[list[int], str]:
    if Image is None:
        raise RuntimeError("Pillow is unavailable")
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        if bbox is not None:
            values = [float(item) for item in bbox]
            if any(value != int(value) for value in values):
                raise ValueError("source_bbox must be pixel-aligned")
            x, y, width, height = (int(value) for value in values)
            if x < 0 or y < 0 or width <= 0 or height <= 0:
                raise ValueError("source_bbox must be positive")
            if x + width > rgba.width or y + height > rgba.height:
                raise ValueError("source_bbox exceeds source image bounds")
            rgba = rgba.crop((x, y, x + width, y + height))
        return [rgba.width, rgba.height], hashlib.sha256(rgba.tobytes()).hexdigest()


def assets_from(data: dict) -> list[dict]:
    assets = data.get("assets")
    if assets is not None:
        return [item for item in assets if isinstance(item, dict)] if isinstance(assets, list) else []
    result: list[dict] = []
    for layer in ("background", "frame_raw"):
        if isinstance(data.get(layer), dict):
            result.append(data[layer] | {"layer": layer})
    if isinstance(data.get("icons"), list):
        result.extend(item | {"layer": "icons"} for item in data["icons"] if isinstance(item, dict))
    return result


def resolve(root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--report")
    args = parser.parse_args()
    manifest = Path(args.manifest).resolve()
    issues: list[dict] = []
    records: list[dict] = []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/source-crop-integrity/v1", "valid": False, "status": "blocked", "issues": [{"severity": "blocker", "code": "manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"}]}
        if args.report:
            atomic_write_json(Path(args.report).resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 2
    if not isinstance(data, dict):
        add(issues, "manifest_not_object")
        data = {}
    root = manifest.parent
    source_reuse_count = 0
    verified_count = 0
    for index, asset in enumerate(assets_from(data)):
        mode = asset.get("provenance_mode") or data.get("provenance_mode") or "imagegen"
        if mode != "source_reuse":
            continue
        source_reuse_count += 1
        asset_id = asset.get("asset_id") or asset.get("id") or f"asset-{index + 1}"
        source_path = resolve(root, asset.get("source_ref"))
        copied_path = resolve(root, asset.get("copied_to"))
        bbox = asset.get("source_bbox")
        policy = asset.get("source_crop_policy")
        declared_crop_hash = asset.get("source_crop_sha256")
        record = {"asset_id": asset_id, "source_bbox": bbox, "source_crop_policy": policy}
        if source_path is None or not source_path.is_file():
            add(issues, "source_file_missing", asset_index=index, asset_id=asset_id, path=str(source_path) if source_path else None)
            continue
        if copied_path is None or not copied_path.is_file():
            add(issues, "copied_asset_missing", asset_index=index, asset_id=asset_id, path=str(copied_path) if copied_path else None)
            continue
        if policy not in POLICIES:
            add(issues, "source_crop_policy_missing", asset_index=index, asset_id=asset_id, expected=sorted(POLICIES))
        if not isinstance(declared_crop_hash, str) or len(declared_crop_hash) != 64:
            add(issues, "source_crop_hash_missing_or_invalid", asset_index=index, asset_id=asset_id)
        try:
            source_size, source_crop_hash = pixel_digest(source_path, bbox)
            record.update({"source_crop_size": source_size, "observed_source_crop_sha256": source_crop_hash})
            if declared_crop_hash != source_crop_hash:
                add(issues, "source_crop_hash_mismatch", asset_index=index, asset_id=asset_id, declared_sha256=declared_crop_hash, observed_sha256=source_crop_hash)
            if policy == "exact":
                copied_size, copied_hash = pixel_digest(copied_path)
                record.update({"copied_asset_size": copied_size, "copied_asset_pixel_sha256": copied_hash})
                if copied_size != source_size or copied_hash != source_crop_hash:
                    add(issues, "source_crop_pixels_mismatch", asset_index=index, asset_id=asset_id, source_crop_size=source_size, copied_asset_size=copied_size, source_crop_sha256=source_crop_hash, copied_asset_pixel_sha256=copied_hash)
                else:
                    verified_count += 1
            elif policy == "derived" and declared_crop_hash == source_crop_hash:
                verified_count += 1
        except Exception as exc:
            add(issues, "source_crop_pixel_check_failed", asset_index=index, asset_id=asset_id, message=f"{type(exc).__name__}: {exc}")
        records.append(record)
    result = {
        "schema": "ai-ppt-plus/source-crop-integrity/v1",
        "manifest": str(manifest),
        "status": "passed" if not issues else "blocked",
        "valid": not issues,
        "source_reuse_count": source_reuse_count,
        "verified_count": verified_count,
        "records": records,
        "issues": issues,
        "human_visual_review_required": True,
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
