from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def test_exact_source_locked_crop(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (20, 10), (255, 255, 255)).save(source)
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"assets": [{"id": "icon", "bbox": [2, 3, 5, 4]}]}), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "extract_reference_assets.py"), str(source), str(spec), str(tmp_path / "assets"), "--manifest", str(manifest)],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["valid"] is True
    assert data["assets"][0]["source_bbox"] == {"x": 2, "y": 3, "w": 5, "h": 4}
    assert Image.open(data["assets"][0]["asset_path"]).size == (5, 4)
