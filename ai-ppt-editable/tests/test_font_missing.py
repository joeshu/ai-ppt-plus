#!/usr/bin/env python3
"""Missing portable font assets must block instead of falling back silently."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="font-missing-") as temp:
        font_dir = Path(temp) / "fonts"
        font_dir.mkdir()
        missing = "missing.otf"
        (font_dir / "font-manifest.json").write_text(json.dumps({
            "file": missing,
            "family": "Missing Fixture",
            "sha256": hashlib.sha256(b"missing").hexdigest(),
            "license": "fixture",
            "license_url": "https://example.invalid/license",
        }), encoding="utf-8")
        report = Path(temp) / "report.json"
        checked = subprocess.run([sys.executable, "scripts/validate_font_asset.py", "--font-dir", str(font_dir), "--report", str(report), "--require-cjk"], cwd=ROOT, capture_output=True, text=True, check=False)
        assert checked.returncode == 2, checked.stdout + checked.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert any(item["code"] == "font_file_missing" for item in data["issues"])
    print("font missing gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
