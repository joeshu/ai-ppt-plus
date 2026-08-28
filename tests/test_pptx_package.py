#!/usr/bin/env python3
"""PPTX package regression: relationships must point at real OOXML parts."""
from __future__ import annotations

import json
import posixpath
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pptx-package-") as temp:
        root = Path(temp)
        deck_spec = root / "deck.json"
        deck_spec.write_text(json.dumps({
            "slide_width_in": 4,
            "slide_height_in": 2.25,
            "slides": [{"texts": [{"object_id": "title", "text": "Package fixture", "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.2, "size": 20}]}],
        }), encoding="utf-8")
        deck = root / "deck.pptx"
        composed = subprocess.run([sys.executable, "scripts/compose_pptx.py", str(deck_spec), str(deck)], cwd=ROOT, capture_output=True, text=True, check=False)
        assert composed.returncode == 0, composed.stdout + composed.stderr
        with zipfile.ZipFile(deck) as package:
            names = set(package.namelist())
            assert "[Content_Types].xml" in names and "ppt/presentation.xml" in names
            assert all(not name.startswith("/") and ".." not in Path(name).parts for name in names)
            rels = [name for name in names if name.endswith(".rels")]
            assert rels
            for rel_path in rels:
                root_xml = ET.fromstring(package.read(rel_path))
                base = Path(rel_path).parent.parent if rel_path.endswith("/_rels/.rels") else Path(rel_path).parent.parent
                source_part = Path(rel_path).parent.parent / Path(rel_path).name.replace(".rels", "")
                for relation in root_xml:
                    target = relation.get("Target")
                    if not target or target.startswith("http"):
                        continue
                    normalized = posixpath.normpath(posixpath.join(source_part.parent.as_posix(), target)).lstrip("/") if not target.startswith("/") else posixpath.normpath(target.lstrip("/"))
                    assert normalized in names, (rel_path, target, normalized)
    print("PPTX package unzip contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
