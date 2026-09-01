#!/usr/bin/env python3
"""Regression test for source-reuse pixel-to-bbox binding."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_source_crop_integrity.py"


def digest(image: Image.Image) -> str:
    return hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()


def run(manifest: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), str(manifest)], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="source-crop-integrity-") as temp:
        root = Path(temp)
        source = Image.new("RGBA", (40, 40), (245, 240, 230, 255))
        for x in range(8, 32):
            for y in range(6, 18):
                source.putpixel((x, y), (210, 140, 30, 255))
        source.putpixel((8, 6), (1, 2, 3, 255))
        source.putpixel((24, 6), (4, 5, 6, 255))
        source_path = root / "source.png"
        source.save(source_path)
        crop = source.crop((8, 6, 24, 18))
        copied_path = root / "copied.png"
        crop.save(copied_path)
        manifest = root / "imagegen-assets-manifest.json"
        payload = {
            "provenance_mode": "source_reuse",
            "assets": [{
                "asset_id": "icon-01",
                "source_ref": "source.png",
                "source_bbox": [8, 6, 16, 12],
                "source_crop_policy": "exact",
                "source_crop_sha256": digest(crop),
                "copied_to": "copied.png",
            }],
        }
        manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        good = run(manifest)
        assert good.returncode == 0, good.stdout + good.stderr
        assert json.loads(good.stdout)["verified_count"] == 1

        wrong_path = root / "wrong.png"
        source.crop((9, 6, 25, 18)).save(wrong_path)
        payload["assets"][0]["copied_to"] = "wrong.png"
        wrong_manifest = root / "wrong-manifest.json"
        wrong_manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        bad = run(wrong_manifest)
        assert bad.returncode == 2 and "source_crop_pixels_mismatch" in bad.stdout, bad.stdout

    print("source crop integrity: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
