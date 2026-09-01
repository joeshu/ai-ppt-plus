#!/usr/bin/env python3
"""Regression test for portable layout-relative resource paths."""
from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def synthetic_sfnt(family: str) -> bytes:
    """Create the minimal valid SFNT used by the embedding regression."""
    head = bytearray(54)
    head[0:4] = struct.pack(">I", 0x00010000)
    head[18:20] = struct.pack(">H", 1000)
    head[44:46] = struct.pack(">H", 0)
    os2 = bytearray(86)
    os2[0:2] = struct.pack(">H", 4)
    os2[4:6] = struct.pack(">H", 400)
    os2[8:10] = struct.pack(">H", 0)
    os2[32:42] = bytes((2, 11, 5, 2, 2, 2, 2, 2, 2, 4))
    os2[42:58] = b"\x00" * 16
    os2[62:64] = struct.pack(">H", 0)
    os2[78:86] = b"\x00" * 8

    records = []
    storage = bytearray()
    for name_id, value in ((1, family), (2, "Regular"), (4, family + " Regular"), (5, "Version 1.0")):
        encoded = value.encode("utf-16-be")
        records.append(struct.pack(">HHHHHH", 3, 1, 0x0804, name_id, len(encoded), len(storage)))
        storage.extend(encoded)
    name = struct.pack(">HHH", 0, len(records), 6 + 12 * len(records)) + b"".join(records) + storage

    tables = [(b"OS/2", bytes(os2)), (b"head", bytes(head)), (b"name", bytes(name))]
    directory_size = 12 + 16 * len(tables)
    offset = (directory_size + 3) & ~3
    directory = bytearray(struct.pack(">IHHHH", 0x4F54544F, len(tables), 0, 0, 0))
    payload = bytearray(b"\x00" * (offset - directory_size))
    for tag, table in tables:
        offset = (directory_size + len(payload) + 3) & ~3
        payload.extend(b"\x00" * (offset - (directory_size + len(payload))))
        directory.extend(struct.pack(">4sIII", tag, 0, offset, len(table)))
        payload.extend(table)
    return bytes(directory + payload)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="editable-relative-paths-") as temp:
        root = Path(temp)
        assets = root / "assets"
        fonts = root / "fonts"
        assets.mkdir()
        fonts.mkdir()
        Image.new("RGB", (24, 24), "#EAF2FF").save(assets / "background.png")

        family = "Relative Path Fixture"
        font_path = fonts / "fixture.otf"
        font_path.write_bytes(synthetic_sfnt(family))
        (fonts / "font-manifest.json").write_text(json.dumps({
            "file": "fixture.otf",
            "family": family,
            "sha256": hashlib.sha256(font_path.read_bytes()).hexdigest(),
            "license": "synthetic regression fixture",
        }), encoding="utf-8")

        layout = root / "layout.json"
        layout.write_text(json.dumps({
            "slide_width_in": 4,
            "slide_height_in": 2.25,
            "units": "fraction",
            "assets_dir": "assets",
            "font_dir": "fonts",
            "font_manifest": "fonts/font-manifest.json",
            "slides": [{
                "background": "background.png",
                "texts": [{"object_id": "title", "text": "relative assets", "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2, "size": 18}],
            }],
        }), encoding="utf-8")
        output = root / "deck.pptx"
        report = root / "embedding.json"
        checked = subprocess.run([
            sys.executable, "scripts/compose_pptx.py", str(layout), str(output),
            "--font-dir", str(fonts), "--embed-fonts", "--embedding-report", str(report),
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        assert checked.returncode == 0, checked.stdout + checked.stderr
        assert output.is_file() and output.stat().st_size > 0
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["valid"] is True and data["fonts"], data
        assert data["fonts"][0]["family"] == family, data
    print("relative layout resource paths: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
