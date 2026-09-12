#!/usr/bin/env python3
"""Regression coverage for DrawingML rich-text child ordering."""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from normalize_ooxml_rich_text import normalize_xml  # noqa: E402


A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def names(element: ET.Element) -> list[str]:
    return [child.tag.rsplit("}", 1)[-1] for child in element]


def main() -> int:
    payload = f'''<root xmlns:a="{A}">
      <a:rPr><a:latin/><a:solidFill/><a:ea/><a:cs/></a:rPr>
      <a:defRPr><a:ea/><a:latin/><a:solidFill/></a:defRPr>
      <a:endParaRPr><a:cs/><a:solidFill/><a:latin/></a:endParaRPr>
    </root>'''.encode()
    normalized, changes, issues = normalize_xml(payload, strict=True)
    assert issues == []
    assert len(changes) == 3
    root = ET.fromstring(normalized)
    expected = ["solidFill", "latin", "ea", "cs"]
    assert names(root[0]) == expected
    assert names(root[1]) == ["solidFill", "latin", "ea"]
    assert names(root[2]) == ["solidFill", "latin", "cs"]

    unknown = f'<a:rPr xmlns:a="{A}"><a:latin/><a:unknown/></a:rPr>'.encode()
    _, _, issues = normalize_xml(unknown, strict=True)
    assert any(item["code"] == "unknown_rich_text_child" for item in issues)
    print("OOXML rich-text child ordering: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
