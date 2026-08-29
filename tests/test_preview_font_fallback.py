#!/usr/bin/env python3
"""A local regular font must not be reused as a fake bold face."""
from __future__ import annotations

import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from preview_renderer import find_cjk_font  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="preview-font-fallback-") as temp:
        font_dir = Path(temp)
        regular = font_dir / "NotoSans-Regular.ttf"
        regular.write_bytes(b"fixture")
        assert find_cjk_font(font_dir, bold=False) == str(regular)
        assert find_cjk_font(font_dir, bold=True) is None

        bold = font_dir / "NotoSans-Bold.ttf"
        bold.write_bytes(b"fixture")
        assert find_cjk_font(font_dir, bold=True) == str(bold)
    print("preview bold fallback: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
