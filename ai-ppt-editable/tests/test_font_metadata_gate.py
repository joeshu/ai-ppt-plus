#!/usr/bin/env python3
"""Regular-looking runtime font assets must carry regular-like SFNT metadata."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_runtime_fonts import materialize_runtime_face  # noqa: E402
from validate_font_asset import inspect_font_metadata  # noqa: E402
from runtime_fonts import resolve_font_file  # noqa: E402


def main() -> int:
    runtime_font = resolve_font_file("Noto Sans CJK SC", bold=False)
    assert runtime_font is not None and runtime_font.is_file(), "runtime CJK regular font unresolved"
    metadata, error = inspect_font_metadata(runtime_font)
    assert error is None, error
    assert metadata and 300 <= metadata["weight_class"] <= 700, metadata

    with tempfile.TemporaryDirectory(prefix="font-metadata-gate-") as temp:
        work = Path(temp)
        thin = work / "NotoSansSC-Regular.ttf"
        record = materialize_runtime_face(runtime_font, thin, "Noto Sans CJK SC", bold=False)
        assert record["standalone_sfnt"] is True
        assert thin.read_bytes()[:4] != b"ttcf", "runtime cache must not disguise TTC bytes as TTF"
        from fontTools.ttLib import TTFont

        font = TTFont(str(thin))
        font["OS/2"].usWeightClass = 100
        font.save(str(thin))
        font.close()
        manifest = work / "font-manifest.json"
        manifest.write_text(json.dumps({
            "file": thin.name,
            "family": "Noto Sans CJK SC",
            "role": "portable_cjk_fallback",
            "sha256": hashlib.sha256(thin.read_bytes()).hexdigest(),
            "license": "fixture",
            "license_url": "https://example.invalid/license",
        }), encoding="utf-8")
        report = work / "report.json"
        checked = subprocess.run(
            [sys.executable, "scripts/validate_font_asset.py", "--font-dir", str(work), "--report", str(report)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        assert checked.returncode == 2, checked.stdout + checked.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert "font_weight_mismatch" in {item["code"] for item in data["issues"]}
    print("font metadata gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
