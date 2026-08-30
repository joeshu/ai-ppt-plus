#!/usr/bin/env python3
"""Regression coverage for shared-runtime drift detection."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    report = Path(tempfile.mkdtemp(prefix="mirror-report-")) / "mirror.json"
    valid = run("scripts/validate_runtime_mirror.py", "--report", str(report))
    assert valid.returncode == 0, valid.stdout + valid.stderr
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["valid"] is True and len(data["pairs"]) == 2, data

    with tempfile.TemporaryDirectory(prefix="mirror-copy-") as temp:
        clone = Path(temp)
        for name in ("scripts", "references", "assets"):
            shutil.copytree(ROOT / name, clone / name)
        shutil.copytree(ROOT / "ai-ppt-visual-gen", clone / "ai-ppt-visual-gen")
        drifted = clone / "ai-ppt-visual-gen" / "scripts" / "atomic_output.py"
        drifted.write_text(drifted.read_text(encoding="utf-8") + "\n# deliberate drift fixture\n", encoding="utf-8")
        broken = run(
            str(ROOT / "scripts" / "validate_runtime_mirror.py"),
            "--root", str(clone), "--worker", "ai-ppt-visual-gen",
            "--report", str(clone / "mirror-broken.json"),
        )
        assert broken.returncode == 2 and "mirror_hash_mismatch" in broken.stdout, broken.stdout

    print("runtime mirror drift guard: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
