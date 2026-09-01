#!/usr/bin/env python3
"""Regression tests for the CPU retrieval index and split-leakage gate."""
from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_retrieval_index.py"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="retrieval-index-") as temp:
        root = Path(temp)
        records = root / "records.jsonl"
        manifest = root / "manifest.json"
        index = root / "index.json"
        evaluation = root / "evaluation.json"
        records.write_text("\n".join([
            json.dumps({"example_id": "case-train:candidate", "split": "train", "task": "reconstruct", "source": [{"sha256": "a" * 64}], "target": {"deck": {}}, "supervision": {"profile": "hybrid", "metrics": {}}}),
            json.dumps({"example_id": "case-test:candidate", "split": "test", "task": "reconstruct", "source": [{"sha256": "b" * 64}], "target": {"deck": {}}, "supervision": {"profile": "hybrid", "metrics": {}}}),
        ]) + "\n", encoding="utf-8")
        manifest.write_text(json.dumps({"schema": "ai-ppt-plus/distillation-training-dataset/v1", "retrieval_ready": True, "records_sha256": hashlib.sha256(records.read_bytes()).hexdigest()}), encoding="utf-8")
        built = subprocess.run([sys.executable, str(SCRIPT), "--records", str(records), "--manifest", str(manifest), "--index", str(index), "--evaluation", str(evaluation)], capture_output=True, text=True, check=False)
        assert built.returncode == 0, built.stdout + built.stderr
        data = json.loads(index.read_text(encoding="utf-8"))
        report = json.loads(evaluation.read_text(encoding="utf-8"))
        assert data["cpu_only"] is True and data["trainable_weights"] is False
        assert report["status"] == "passed" and report["holdout_count"] == 1

        records.write_text(records.read_text(encoding="utf-8").replace("b" * 64, "a" * 64), encoding="utf-8")
        manifest.write_text(json.dumps({"schema": "ai-ppt-plus/distillation-training-dataset/v1", "retrieval_ready": True, "records_sha256": hashlib.sha256(records.read_bytes()).hexdigest()}), encoding="utf-8")
        leaked = subprocess.run([sys.executable, str(SCRIPT), "--records", str(records), "--manifest", str(manifest), "--index", str(index), "--evaluation", str(evaluation)], capture_output=True, text=True, check=False)
        assert leaked.returncode == 2, leaked.stdout + leaked.stderr
        report = json.loads(evaluation.read_text(encoding="utf-8"))
        assert report["status"] == "blocked" and any(item["code"] == "source_leakage" for item in report["issues"])
    print("CPU retrieval index: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
