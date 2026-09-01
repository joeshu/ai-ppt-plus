#!/usr/bin/env python3
"""Regression tests for ZIP-level PPTX compatibility repair."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
NORMALIZER = ROOT / "scripts" / "normalize_ooxml_relationships.py"
INVARIANTS = ROOT / "scripts" / "validate_repackaging_invariants.py"


def write_fixture(path: Path, missing_picture: bool = False) -> None:
    slide = """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld><p:spTree>
    <p:pic/>
    <p:sp><a:r><a:rPr b="1"><a:solidFill><a:srgbClr val="FF0000"/></a:solidFill></a:rPr><a:t>红</a:t></a:r>
      <a:r><a:rPr sz="1200"><a:t>字</a:t></a:rPr></a:r>
    </p:sp>
    <a:gradFill/>
  </p:spTree></p:cSld>
</p:sld>"""
    if missing_picture:
        slide = slide.replace("    <p:pic/>\n", "")
    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="x" Target="/ppt/media/icon.png"/>
</Relationships>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="x" Target="/ppt/presentation.xml"/>
</Relationships>"""
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("ppt/slides/slide1.xml", slide)
        archive.writestr("ppt/slides/_rels/slide1.xml.rels", rels)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("ppt/media/icon.png", b"icon")


def run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(script), *args], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ooxml-compatibility-") as temp:
        root = Path(temp)
        before = root / "before.pptx"
        after = root / "after.pptx"
        broken = root / "broken.pptx"
        normalized = root / "normalized.pptx"
        write_fixture(before)
        write_fixture(broken, missing_picture=True)
        good = run(NORMALIZER, str(before), str(after))
        assert good.returncode == 0, good.stdout + good.stderr
        with ZipFile(after) as archive:
            assert b'Target="../media/icon.png"' in archive.read("ppt/slides/_rels/slide1.xml.rels")
            assert b'Target="ppt/presentation.xml"' in archive.read("_rels/.rels")
        invariant_ok = run(INVARIANTS, str(before), str(after))
        assert invariant_ok.returncode == 0, invariant_ok.stdout + invariant_ok.stderr
        invariant_bad = run(INVARIANTS, str(before), str(broken))
        assert invariant_bad.returncode == 2 and "pictures" in invariant_bad.stdout, invariant_bad.stdout
        bad_normalizer = run(NORMALIZER, str(broken), str(normalized))
        assert bad_normalizer.returncode == 0, bad_normalizer.stdout + bad_normalizer.stderr
    print("ooxml compatibility: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
