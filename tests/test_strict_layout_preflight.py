#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from strict_layout_preflight import validate


def _cjk_fixture(source: Path, target: Path) -> None:
    from fontTools.ttLib import TTFont

    font = TTFont(str(source))
    try:
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[0x4E2D] = "A"
                table.cmap[0x56FD] = "B"
                table.cmap[0x4E1A] = "C"
                table.cmap[0x52A1] = "D"
        font.save(str(target))
    finally:
        font.close()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="strict-layout-") as temp:
        root = Path(temp)
        layout = root / "deck.json"
        layout.write_text("{}", encoding="utf-8")
        deck = {"slides": [{"texts": [{"object_id": "title", "text": "中文标题"}]}]}

        missing = validate(layout, deck)
        assert not missing["valid"]
        assert {item["code"] for item in missing["issues"]} == {"strict_cjk_font_coverage_missing"}

        font_dir = root / "fonts"
        font_dir.mkdir()
        latin = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        if latin.is_file():
            (font_dir / "latin.ttf").write_bytes(latin.read_bytes())
            false_fallback = validate(layout, deck, font_dir=str(font_dir))
            assert not false_fallback["valid"]
            assert false_fallback["font_candidates"][0]["cjk_coverage_valid"] is False

            _cjk_fixture(latin, font_dir / "cjk-test.ttf")
            covered = validate(layout, deck, font_dir=str(font_dir))
            assert covered["valid"], json.dumps(covered, ensure_ascii=False)
            assert any(item["cjk_coverage_valid"] for item in covered["font_candidates"])

        symbol = validate(layout, {"slides": [{"texts": [{"object_id": "fake-icon", "text": "☎"}]}]})
        assert not symbol["valid"]
        issue = next(item for item in symbol["issues"] if item["code"] == "strict_symbol_glyph_visual_forbidden")
        assert issue["objects"][0]["object_id"] == "fake-icon"

        allowed = validate(layout, {"slides": [{"texts": [{"object_id": "literal-symbol", "text": "☎", "allow_symbol_glyph": True}]}]})
        assert allowed["valid"]
    print("strict layout font/icon preflight: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
