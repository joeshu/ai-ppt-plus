"""Regression test for the full-decode source-image gate."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    try:
        from PIL import Image
    except ImportError:
        print("source image decode gate: skipped (Pillow unavailable)")
        return 0

    with tempfile.TemporaryDirectory(prefix="source-image-validation-") as temp:
        work = Path(temp)
        valid = work / "valid.png"
        Image.new("RGBA", (4, 3), (12, 34, 56, 255)).save(valid)
        broken = work / "broken.png"
        broken.write_bytes(valid.read_bytes()[:-8])

        good_report = work / "good.json"
        good = subprocess.run(
            [sys.executable, "scripts/validate_source_images.py", str(valid), "--report", str(good_report)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert good.returncode == 0, good.stdout + good.stderr
        assert json.loads(good_report.read_text(encoding="utf-8"))["valid"] is True

        bad_report = work / "bad.json"
        bad = subprocess.run(
            [sys.executable, "scripts/validate_source_images.py", str(broken), "--report", str(bad_report)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert bad.returncode == 2, bad.stdout + bad.stderr
        data = json.loads(bad_report.read_text(encoding="utf-8"))
        assert data["valid"] is False
        assert data["issues"][0]["code"] == "source_image_not_decodable"

    print("source image full-decode gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
