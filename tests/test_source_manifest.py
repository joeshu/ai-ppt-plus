#!/usr/bin/env python3
"""Regression coverage for hash-bound reproducible-build manifests."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_source_manifest.py"
SHA = "5377f8c5e1edf4b4481a344637027b9748e507ff"


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        qa = folder / "qa"
        qa.mkdir()
        files = {}
        for name, data in (("input.png", b"image"), ("font.ttf", b"font"), ("asset.png", b"asset"), ("build.mjs", b"builder"), ("final.pptx", b"pptx")):
            path = folder / name
            path.write_bytes(data)
            files[name] = path
        for name in ("render.json", "finalizer.json", "authoring.json"):
            (qa / name).write_text(json.dumps({"valid": True}), encoding="utf-8")
        report = folder / "manifest.json"
        completed = subprocess.run([
            sys.executable, str(SCRIPT), "--input", str(files["input.png"]), "--font", str(files["font.ttf"]),
            "--asset", str(files["asset.png"]), "--build-script", str(files["build.mjs"]),
            "--pptx", str(files["final.pptx"]), "--qa-dir", str(qa), "--repo-sha", SHA,
            "--render-report", str(qa / "render.json"), "--finalizer-receipt", str(qa / "finalizer.json"),
            "--authoring-contract", str(qa / "authoring.json"), "--render-tool", "@oai/artifact-tool@2.8.59",
            "--strict", "--output", str(report),
        ], cwd=ROOT, text=True, capture_output=True, check=False)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        result = json.loads(report.read_text(encoding="utf-8"))
        assert result["valid"] is True
        assert result["repository_sha"] == SHA
        assert len(result["inputs"][0]["sha256"]) == 64
    print("source manifest: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
