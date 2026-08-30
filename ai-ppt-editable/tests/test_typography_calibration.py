#!/usr/bin/env python3
"""Regression tests for prominent-text metric calibration."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="typography-calibration-") as temp:
        root = Path(temp)
        manifest = root / "typography-calibration.json"
        base = {
            "schema": "ai-ppt-plus/typography-calibration/v1",
            "coordinate_space": "normalized_pixel",
            "canvas": {"width": 1262, "height": 710},
            "font_profile": {"source_family": "Microsoft YaHei", "render_family": "Noto Sans SC"},
            "samples": [{
                "sample_id": "title",
                "role": "title",
                "source_ink_bbox": [150, 20, 420, 42],
                "rendered_ink_bbox": [150, 20, 400, 40],
                "declared_size_px": 34,
            }],
        }
        write(manifest, base)
        report = root / "report.json"
        checked = run("scripts/validate_typography_calibration.py", str(manifest), "--report", str(report))
        assert checked.returncode == 0, checked.stdout + checked.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["valid"] is True
        assert data["samples"][0]["recommended_size_px"] == 35.7

        drift = dict(base)
        drift["samples"] = [dict(base["samples"][0], rendered_ink_bbox=[150, 20, 250, 24])]
        write(manifest, drift)
        failed = run("scripts/validate_typography_calibration.py", str(manifest))
        assert failed.returncode == 2
        assert "typography_metric_drift" in failed.stdout

        # A reference route must fail before the expensive render graph when
        # the required evidence is absent. This keeps a missing calibration
        # from consuming a full LibreOffice/Poppler pass.
        project = root / "reference-project"
        project.mkdir()
        deck = project / "deck.pptx"
        deck.write_bytes(b"placeholder deck")
        reference = project / "reference.png"
        reference.write_bytes(b"placeholder reference")
        route = project / "route.json"
        write(route, {"status": "decided", "route": "reference-reconstruction"})
        missing = run(
            "scripts/run_pipeline.py", str(project), "--deck", str(deck),
            "--expected-pages", "1", "--route-decision", str(route),
            "--require-route", "--reference", str(reference),
        )
        assert missing.returncode == 2
        assert "typography_calibration_missing" in missing.stdout

    print("typography calibration gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
