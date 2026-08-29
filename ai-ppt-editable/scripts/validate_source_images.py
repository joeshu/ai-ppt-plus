#!/usr/bin/env python3
"""Verify that raster source images are fully decodable before analysis.

Image metadata and a successful file open are not enough for a reconstruction
pipeline: truncated IDAT/JPEG data can survive a copy and fail later during
OCR, chroma-key extraction, or rendering.  This gate verifies the image
structure and then forces a complete pixel decode in a fresh handle.

Usage: validate_source_images.py IMAGE [...] --report report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from atomic_output import atomic_write_json


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_image(path: Path) -> dict:
    record = {"path": str(path), "exists": path.is_file(), "decoded": False}
    if not path.is_file():
        record["error"] = "file_not_found"
        return record
    record["bytes"] = path.stat().st_size
    record["sha256"] = sha256(path)
    try:
        from PIL import Image
    except ImportError as exc:
        record["error"] = f"pillow_unavailable: {exc}"
        return record
    try:
        # verify() checks container integrity without leaving a partially
        # decoded object behind; reopen and load() to force all pixel data.
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            record.update({
                "format": image.format,
                "mode": image.mode,
                "width": width,
                "height": height,
                "decoded": width > 0 and height > 0,
            })
            if width <= 0 or height <= 0:
                record["error"] = "invalid_dimensions"
    except Exception as exc:  # Pillow raises format-specific exceptions.
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", help="source raster image paths")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    records = [inspect_image(Path(value).resolve()) for value in args.images]
    issues = [
        {
            "severity": "blocker",
            "code": "source_image_not_decodable",
            "path": record["path"],
            "message": record.get("error", "full pixel decode failed"),
        }
        for record in records
        if record.get("decoded") is not True
    ]
    result = {
        "schema": "ai-ppt-plus/source-image-validation/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "images": records,
        "issues": issues,
    }
    atomic_write_json(args.report, result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
