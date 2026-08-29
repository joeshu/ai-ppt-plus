#!/usr/bin/env python3
"""Regression tests for the strict, project-wide asset hash gate."""
from __future__ import annotations

import hashlib
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
    with tempfile.TemporaryDirectory(prefix="asset-hashes-") as temp:
        root = Path(temp)
        asset = root / "asset.bin"
        asset.write_bytes(b"stable asset")
        digest = hashlib.sha256(asset.read_bytes()).hexdigest()
        manifest = root / "asset-manifest.json"
        write(manifest, {"schema": "ai-ppt-plus/assets/v1", "assets": [{"asset_id": "a", "path": "asset.bin", "sha256": digest}]})
        report = root / "hash-report.json"
        checked = run("scripts/validate_asset_hashes.py", str(manifest), "--base", str(root), "--require", "--report", str(report))
        assert checked.returncode == 0, checked.stdout + checked.stderr
        assert json.loads(report.read_text(encoding="utf-8"))["checked_count"] == 1

        broken = json.loads(manifest.read_text(encoding="utf-8"))
        broken["assets"][0].pop("sha256")
        write(manifest, broken)
        failed = run("scripts/validate_asset_hashes.py", str(manifest), "--base", str(root), "--require")
        assert failed.returncode == 2 and "asset_hash_missing" in failed.stdout, failed.stdout

        imagegen = root / "imagegen-assets-manifest.json"
        copied = root / "generated.png"
        copied.write_bytes(b"png-ish")
        write(imagegen, {"assets": [{"generated_source": "source", "copied_to": "generated.png", "layer": "background", "prompt_file": "prompt.txt", "backend": "codex-imagegen", "key_color": "#00ff00", "sha256": hashlib.sha256(copied.read_bytes()).hexdigest()}]})
        (root / "prompt.txt").write_text("prompt", encoding="utf-8")
        specialized = run("scripts/validate_imagegen_assets_manifest.py", str(imagegen), "--require-hashes")
        assert specialized.returncode == 0, specialized.stdout + specialized.stderr

    print("asset hash gates: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
