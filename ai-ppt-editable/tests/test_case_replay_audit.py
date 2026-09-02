#!/usr/bin/env python3
"""Regression test for the case-level native replay gate."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_object_manifest import build  # noqa: E402


def run(*args: str):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="case-replay-audit-") as temp:
        root = Path(temp)
        layout_value = {
            "slide_width_in": 4,
            "slide_height_in": 2.25,
            "units": "fraction",
            "assets_dir": str(root),
            "theme": {"font": "Noto Sans CJK SC", "text_color": "#FFFFFF", "table_header_fill": "#9B0B1B", "table_fill": "#F5F8FC"},
            "slides": [{
                "shapes": [{"object_id": "background", "type": "rect", "x": 0, "y": 0, "w": 1, "h": 1, "fill": "#061A35"}],
                "groups": [{"object_id": "native-panel", "role": "semantic-panel", "native_required": True, "x": 0.05, "y": 0.05, "w": 0.35, "h": 0.3, "children_coordinate_space": "local", "children": [{"object_id": "native-panel-fill", "type": "rounded_rect", "x": 0, "y": 0, "w": 1, "h": 1, "fill": "#0C2B4D"}]}],
                "tables": [{"object_id": "merged-table", "native_required": True, "x": 0.45, "y": 0.1, "w": 0.45, "h": 0.6, "rows": [["场景", "状态"], ["发展", {"runs": [{"text": "增收", "bold": True, "color": "#E60012"}, {"text": "有奖", "color": "#061A35"}]}], ["", "减收不罚"]], "merges": [[1, 0, 2, 0]], "rich_text_required": True}],
                "texts": [{"object_id": "formal-title", "text": "原生回放", "x": 0.05, "y": 0.82, "w": 0.4, "h": 0.1, "size": 14}],
            }],
        }
        layout = root / "layout.json"
        layout.write_text(json.dumps(layout_value, ensure_ascii=False, indent=2), encoding="utf-8")
        deck = root / "deck.pptx"
        composed = run("scripts/compose_pptx.py", str(layout), str(deck), "--strict-input", "--require-native-structure")
        assert composed.returncode == 0, composed.stdout + composed.stderr

        manifest = root / "object-manifest.json"
        manifest.write_text(json.dumps(build(layout_value, None, None), ensure_ascii=False, indent=2), encoding="utf-8")
        report = root / "case-replay-audit.json"
        checked = run("scripts/case_replay_audit.py", str(deck), "--object-manifest", str(manifest), "--report", str(report))
        assert checked.returncode == 0, checked.stdout + checked.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["valid"] is True, data
        assert data["native_table_count"] == 1, data
        assert data["a_tbl_count"] == 1, data
        assert data["formal_text_native_count"] == 1, data
        assert data["slides"][0]["tables"][0]["observed_merges"] == [[1, 0, 2, 0]], data
        assert data["slides"][0]["tables"][0]["rich_text_cells"] == 1, data
    print("case replay audit: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
