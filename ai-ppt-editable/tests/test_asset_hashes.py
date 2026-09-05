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

        source = root / "source.png"
        source.write_bytes(b"authoritative source")
        reused = root / "reused.png"
        reused.write_bytes(b"cropped source asset")
        reuse_manifest = root / "source-reuse-manifest.json"
        write(reuse_manifest, {"provenance_mode": "source_reuse", "assets": [{
            "source_ref": "source.png",
            "source_bbox": [10, 20, 30, 40],
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "copied_to": "reused.png",
            "layer": "background",
            "extraction_method": "deterministic_source_crop",
            "sha256": hashlib.sha256(reused.read_bytes()).hexdigest(),
        }]})
        source_reuse = run("scripts/validate_imagegen_assets_manifest.py", str(reuse_manifest), "--require-hashes")
        assert source_reuse.returncode == 0, source_reuse.stdout + source_reuse.stderr
        assert json.loads(source_reuse.stdout)["provenance_modes"] == {"source_reuse": 1}

        icon_reuse = root / "icon-source-reuse-manifest.json"
        write(icon_reuse, {"provenance_mode": "source_reuse", "assets": [{
            "asset_id": "icon-1",
            "asset_class": "icon",
            "source_ref": "source.png",
            "source_bbox": [10, 20, 30, 40],
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "copied_to": "reused.png",
            "layer": "icons_raw_1",
            "extraction_method": "deterministic_source_crop",
            "sha256": hashlib.sha256(reused.read_bytes()).hexdigest(),
        }]})
        blocked_icon = run("scripts/validate_imagegen_assets_manifest.py", str(icon_reuse), "--require-hashes")
        assert blocked_icon.returncode == 2, blocked_icon.stdout + blocked_icon.stderr
        assert "final_asset_route_requires_native_imagegen" in blocked_icon.stdout

        approved = json.loads(icon_reuse.read_text(encoding="utf-8"))
        approved["assets"][0].update({
            "fallback_decision": "user_approved",
            "decision_id": "decision-1",
            "decision_reason": "native imagegen failed and user selected crop fallback",
            "decision_timestamp": "2026-09-05T00:00:00Z",
        })
        write(icon_reuse, approved)
        approved_icon = run("scripts/validate_imagegen_assets_manifest.py", str(icon_reuse), "--require-hashes")
        assert approved_icon.returncode == 0, approved_icon.stdout + approved_icon.stderr

    print("asset hash gates: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
