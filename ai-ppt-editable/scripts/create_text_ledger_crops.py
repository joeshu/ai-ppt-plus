#!/usr/bin/env python3
"""Create enlarged crops for low-confidence text ledger entries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from atomic_output import atomic_write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--reference", action="append", default=[], help="page=image path, repeat")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--threshold", type=float, default=0.97)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    refs = {}
    for item in args.reference:
        page, sep, value = item.partition("=")
        if sep: refs[int(page)] = Path(value).resolve()
    ledger = json.loads(Path(args.ledger).read_text(encoding="utf-8"))
    out_dir = Path(args.output_dir).resolve(); out_dir.mkdir(parents=True, exist_ok=True)
    crops, issues = [], []
    for index, entry in enumerate(ledger.get("entries", [])):
        confidence = float(entry.get("ocr_confidence", 1.0))
        bbox = entry.get("bbox")
        if confidence >= args.threshold or not bbox: continue
        source = refs.get(int(entry.get("page", 1)))
        if not source or not source.is_file():
            issues.append({"severity": "blocker", "code": "low_confidence_reference_missing", "index": index}); continue
        try:
            with Image.open(source) as image:
                x, y, w, h = [int(value) for value in bbox]
                crop = image.crop((x, y, x + w, y + h)).resize((max(w * 4, 4), max(h * 4, 4)))
                target = out_dir / f"entry-{index + 1:03d}.png"; crop.save(target)
                crops.append({"index": index, "path": str(target), "sha256": __import__("hashlib").sha256(target.read_bytes()).hexdigest()})
        except Exception as exc:
            issues.append({"severity": "blocker", "code": "crop_failed", "index": index, "message": str(exc)})
    result = {"schema": "ai-ppt-plus/text-ledger-crops/v1", "valid": not issues, "threshold": args.threshold, "crops": crops, "issues": issues}
    atomic_write_json(Path(args.report).resolve(), result); print(json.dumps(result, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__": raise SystemExit(main())
