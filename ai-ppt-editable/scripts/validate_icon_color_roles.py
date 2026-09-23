#!/usr/bin/env python3
"""Validate the declared foreground color of independently generated icon PNGs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def check(manifest: Path) -> dict:
    config = json.loads(manifest.read_text(encoding="utf-8"))
    if config.get("schema") != "ai-ppt-plus/icon-color-roles/v1":
        raise ValueError("unsupported icon color manifest")
    results = []
    for entry in config["icons"]:
        file = (manifest.parent / entry["path"]).resolve()
        color = entry["foreground_hex"].lstrip("#")
        rgb = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
        tolerance = int(entry.get("tolerance", 32))
        required = float(entry.get("min_fraction", 0.90))
        im = Image.open(file).convert("RGBA")
        pixels = list(im.get_flattened_data())
        visible = [p for p in pixels if p[3] >= 192]
        matches = sum(max(abs(p[k] - rgb[k]) for k in range(3)) <= tolerance for p in visible)
        fraction = matches / len(visible) if visible else 0.0
        corners = [im.getpixel(xy)[3] for xy in ((0, 0), (im.width-1, 0), (0, im.height-1), (im.width-1, im.height-1))]
        ok = fraction >= required and max(corners) == 0
        results.append({"asset_id": entry["asset_id"], "path": str(file), "fraction": round(fraction, 4), "expected": entry["foreground_hex"], "ok": ok})
    return {"ok": all(r["ok"] for r in results), "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = check(args.manifest)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
