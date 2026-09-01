#!/usr/bin/env python3
"""Regression tests for icon, typography, gradient and ratio fidelity gates."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_reference_fidelity.py"


def h(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def run(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), str(path), "--strict"], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="reference-fidelity-") as temp:
        root = Path(temp)
        good = {
            "schema": "ai-ppt-plus/reference-fidelity/v1",
            "source": {"path": "source.png", "size": [1536, 1024]},
            "candidate": {"path": "candidate.pptx", "size": [1920, 1080]},
            "aspect_ratio_policy": "declared-fit",
            "aspect_ratio_override": {"approved": True, "mapping": "fit-with-protected-margins"},
            "icons": [{"semantic_id": "process-01", "source_bbox": [10, 10, 40, 40], "provenance_mode": "source_reuse", "asset_sha256": h("icon"), "pptx_object_ids": ["icon-1"], "render_bbox": [10, 10, 40, 40], "visual_status": "pass", "placeholder": False}],
            "text_regions": [{"text_id": "title", "text": "标准动作", "source_bbox": [10, 10, 200, 40], "pptx_object_ids": ["text-1"], "runs": [{"text": "标准动作", "style": {"bold": True, "color": "#C9151E"}}], "visual_status": "pass"}],
            "gradient_regions": [{"gradient_id": "footer-wave", "source_bbox": [0, 900, 1536, 124], "treatment": "source_asset", "asset_path": "assets/footer-wave.png", "asset_sha256": h("wave"), "render_visible": True}],
        }
        path = root / "good.json"
        path.write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")
        result = run(path)
        assert result.returncode == 0, result.stdout + result.stderr
        bad = json.loads(json.dumps(good))
        bad["icons"][0]["fallback_symbol"] = "0"
        bad["gradient_regions"][0]["treatment"] = "flat_fill"
        bad_path = root / "bad.json"
        bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        result = run(bad_path)
        assert result.returncode == 2, result.stdout + result.stderr
        report = json.loads(result.stdout)
        codes = {item["code"] for item in report["issues"]}
        assert "icon_placeholder_or_symbol" in codes and "gradient_treatment_missing" in codes
    print("reference fidelity contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
