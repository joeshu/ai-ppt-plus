#!/usr/bin/env python3
"""Regression test for standalone generated illustration layer evidence."""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="icon-layer-standalone-") as temp:
        root = Path(temp)
        (root / "evidence.png").write_bytes(PNG_1X1)
        manifest = root / "icon-assets.json"
        manifest.write_text(json.dumps({
            "schema": "ai-ppt-plus/icon-assets/v1",
            "source_vs_frame_review": "pass",
            "frame_asset_ids": [],
            "icon_asset_ids": ["standalone"],
            "frame_preview": "evidence.png",
            "contact_sheet": "evidence.png",
            "assets": [{"asset_id": "standalone", "frame_exclusion": "not-applicable-standalone"}],
        }), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, "scripts/audit_icon_layers.py", str(manifest)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
    print("standalone illustration layer audit: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
