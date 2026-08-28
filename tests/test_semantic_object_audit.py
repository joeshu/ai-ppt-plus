#!/usr/bin/env python3
"""Regression tests for final-PPTX semantic object auditing."""
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


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def run(*args: str):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="semantic-audit-") as temp:
        root = Path(temp)
        logo = root / "logo.png"
        logo.write_bytes(PNG_1X1)
        layout = root / "layout.json"
        write(layout, {
            "slide_width_in": 4,
            "slide_height_in": 2.25,
            "assets_dir": str(root),
            "slides": [{
                "icons": [{"object_id": "logo", "role": "brand_lockup", "file": "logo.png", "x": 0.8, "y": 0.05, "w": 0.1, "h": 0.1}],
                "texts": [{"object_id": "title", "text": "语义校验", "x": 0.1, "y": 0.1, "w": 0.5, "h": 0.2, "size": 18}],
                "tables": [{"object_id": "table", "x": 0.1, "y": 0.4, "w": 0.3, "h": 0.2, "rows": [["A", "B"], ["1", "2"]]}],
                "charts": [{"object_id": "chart", "type": "column", "x": 0.5, "y": 0.4, "w": 0.3, "h": 0.3, "categories": ["A", "B"], "series": [{"name": "数量", "values": [1, 2]}]}],
            }],
        })
        deck = root / "deck.pptx"
        composed = run("scripts/compose_pptx.py", str(layout), str(deck))
        assert composed.returncode == 0, composed.stdout + composed.stderr

        object_manifest = root / "slide-object-manifest.json"
        write(object_manifest, {"slides": [{"slide_no": 1, "objects": [
            {"object_id": "title", "role": "formal-text", "object_type": "editable_text", "text_spec": {"content": "语义校验"}},
            {"object_id": "table", "role": "data-table", "object_type": "editable_table"},
            {"object_id": "chart", "role": "data-chart", "object_type": "editable_chart"},
            {"object_id": "logo", "role": "brand_lockup", "object_type": "independent_image", "source_path": "logo.png"},
        ]}]})
        report = root / "semantic.json"
        checked = run("scripts/semantic_object_audit.py", str(deck), "--object-manifest", str(object_manifest), "--report", str(report))
        assert checked.returncode == 0, checked.stdout + checked.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["valid"] is True, data
        records = {item["object_id"]: item for item in data["objects"]}
        assert records["title"]["semantic_checks"]["text_exact"] is True
        assert records["table"]["semantic_checks"]["native_table_data"] is True
        assert records["chart"]["semantic_checks"]["native_chart_data"] is True, records["chart"]
        assert records["logo"]["semantic_checks"]["brand_lockup_whole_asset"] is True
        assert records["logo"]["semantic_checks"]["source_hash"] is True

        broken = json.loads(object_manifest.read_text(encoding="utf-8"))
        broken["slides"][0]["objects"][0]["text_spec"]["content"] = "错误文本"
        write(object_manifest, broken)
        failed = run("scripts/semantic_object_audit.py", str(deck), "--object-manifest", str(object_manifest))
        assert failed.returncode == 2 and "pptx_text_manifest_mismatch" in failed.stdout
    print("semantic object audit: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())