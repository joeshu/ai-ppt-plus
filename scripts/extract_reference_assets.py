#!/usr/bin/env python3
"""Extract exact, independently placeable visual assets from a slide reference."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference")
    parser.add_argument("spec", help="JSON with assets containing id and bbox [x,y,w,h]")
    parser.add_argument("out_dir")
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    reference = Path(args.reference).resolve()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir).resolve()
    manifest_path = Path(args.manifest).resolve()
    source = Image.open(reference).convert("RGBA")
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for item in spec.get("assets", []):
        asset_id = str(item["id"])
        x, y, w, h = (int(value) for value in item["bbox"])
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > source.width or y + h > source.height:
            raise ValueError(f"invalid_bbox:{asset_id}:{[x, y, w, h]}")
        output = out_dir / f"{asset_id}.png"
        source.crop((x, y, x + w, y + h)).save(output)
        records.append({
            "asset_id": asset_id,
            "provenance_mode": "source_reuse",
            "source_ref": str(reference),
            "source_sha256": sha256(reference),
            "source_bbox": {"x": x, "y": y, "w": w, "h": h},
            "asset_path": str(output),
            "asset_sha256": sha256(output),
            "extraction_method": "exact_rgba_crop",
            "contains_formal_text": bool(item.get("contains_formal_text", False)),
            "independent": True,
            "replaceable": True,
        })
    result = {
        "schema": "ai-ppt-plus/source-locked-assets/v1",
        "reference": str(reference),
        "reference_sha256": sha256(reference),
        "reference_size": [source.width, source.height],
        "valid": bool(records) and not any(row["contains_formal_text"] for row in records),
        "assets": records,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
