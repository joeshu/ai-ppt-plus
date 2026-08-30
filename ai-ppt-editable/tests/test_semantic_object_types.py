#!/usr/bin/env python3
"""Regression test for native line/connector semantic classification."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="semantic-line-") as temp:
        work = Path(temp)
        layout = work / "layout.json"
        layout.write_text(json.dumps({
            "slide_width_in": 4,
            "slide_height_in": 2.25,
            "slides": [{
                "shapes": [{
                    "object_id": "native-line",
                    "type": "line",
                    "x": 0.5,
                    "y": 0.5,
                    "w": 1.0,
                    "h": 0.01,
                    "line": "#123456",
                    "line_width": 2,
                }],
            }],
        }), encoding="utf-8")
        deck = work / "deck.pptx"
        composed = subprocess.run(
            [sys.executable, "scripts/compose_pptx.py", str(layout), str(deck)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        assert composed.returncode == 0, composed.stdout + composed.stderr

        manifest = work / "object-manifest.json"
        manifest.write_text(json.dumps({
            "schema": "ai-ppt-plus/slide-object-manifest/v1",
            "slides": [{
                "slide_no": 1,
                "objects": [{
                    "object_id": "native-line",
                    "object_type": "native_shape",
                    "editability_level": "L1",
                    "semantic_role": "legend-key",
                }],
            }],
        }), encoding="utf-8")
        report = work / "semantic.json"
        audited = subprocess.run([
            sys.executable, "scripts/semantic_object_audit.py", str(deck),
            "--object-manifest", str(manifest), "--report", str(report),
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        assert audited.returncode == 0, audited.stdout + audited.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["valid"] is True, data
        assert data.get("errors", []) == [], data
    print("native line semantic classification: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
