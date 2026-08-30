#!/usr/bin/env python3
"""Regression tests for the visual-only A5 deck-strip helper."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    try:
        from PIL import Image
    except ImportError:
        print("visual generation strip: skipped (Pillow unavailable)")
        return 0

    with tempfile.TemporaryDirectory(prefix="visual-generation-strip-") as temp:
        root = Path(temp)
        slides = []
        for slide_no, color in enumerate(((20, 60, 70), (40, 120, 125), (220, 90, 70), (240, 220, 180)), start=1):
            path = root / f"slide-{slide_no}.png"
            Image.new("RGB", (160, 90), color).save(path)
            slides.append({
                "slide_no": slide_no,
                "copied_to": path.name,
                "canvas": {"ratio": "16:9"},
            })
        manifest = root / "visual-generation-manifest.json"
        manifest.write_text(json.dumps({
            "schema": "ai-ppt-plus/visual-generation-manifest/v1",
            "project_id": "strip-fixture",
            "slides": slides,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        output = root / "qa" / "deck-strip.png"
        completed = subprocess.run([
            sys.executable, "scripts/build_visual_generation_strip.py", str(manifest),
            "--output", str(output), "--expected-pages", "4", "--columns", "2",
            "--thumbnail-width", "512", "--record-in-manifest",
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        result = json.loads(completed.stdout)
        assert result["valid"] is True and result["recorded_in_manifest"] is True, result
        with Image.open(output) as image:
            assert image.size == (1096, 648), image.size
        updated = json.loads(manifest.read_text(encoding="utf-8"))
        strip = updated["deck_strip"]
        assert strip["path"] == "qa/deck-strip.png"
        assert strip["sha256"] == digest(output)
        assert [item["slide_no"] for item in strip["source_slides"]] == [1, 2, 3, 4]

        cached = subprocess.run([
            sys.executable, "scripts/build_visual_generation_strip.py", str(manifest),
            "--output", str(output), "--expected-pages", "4", "--columns", "2",
            "--thumbnail-width", "512", "--record-in-manifest",
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        assert cached.returncode == 0, cached.stdout + cached.stderr
        cached_result = json.loads(cached.stdout)
        assert cached_result["status"] == "cached" and cached_result["cache_hit"] is True, cached_result
        assert cached_result["output_sha256"] == digest(output), cached_result

    print("visual generation strip: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
