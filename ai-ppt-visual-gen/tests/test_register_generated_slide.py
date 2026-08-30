#!/usr/bin/env python3
"""Regression test for the one-command A4 evidence handoff."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="register-slide-") as temp:
        root = Path(temp)
        visual = root / "visual"
        source_dir = root / "runtime"
        (visual / "slides").mkdir(parents=True)
        source_dir.mkdir()
        prompt = visual / "prompt.md"
        prompt.write_text("prompt\n", encoding="utf-8")
        source = source_dir / "source.png"
        Image.new("RGB", (1672, 941), "white").save(source)
        manifest = visual / "manifest.json"
        manifest.write_text(json.dumps({
            "schema": "ai-ppt-plus/visual-generation-manifest/v1",
            "project_id": "register-fixture",
            "generation_session_id": "session",
            "slides": [],
        }, ensure_ascii=False), encoding="utf-8")
        report = visual / "report.json"
        command = [
            sys.executable,
            str(ROOT / "scripts/register_generated_slide.py"),
            str(manifest),
            "--slide-no", "1",
            "--prompt-file", str(prompt),
            "--source", str(source),
            "--copy-to", "slides/one.png",
            "--backend", "codex-imagegen",
            "--model-or-tool", "Codex built-in image_gen",
            "--report", str(report),
        ]
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        data = json.loads(manifest.read_text(encoding="utf-8"))
        record = data["slides"][0]
        assert record["canvas"] == {"width_px": 1672, "height_px": 941, "ratio": "16:9"}, record
        assert (visual / record["copied_to"]).is_file(), record
        assert json.loads(report.read_text(encoding="utf-8"))["replaced_existing"] is False

        duplicate = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert duplicate.returncode != 0 and "--force" in duplicate.stderr, duplicate.stderr

    print("register generated slide: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
