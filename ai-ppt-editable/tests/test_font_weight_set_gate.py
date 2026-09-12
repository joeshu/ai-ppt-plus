"""A strict font asset run must reject a missing real weight and accept a complete set."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    bundled = ROOT / "assets/fonts/NotoSansSC-Regular.ttf"
    with tempfile.TemporaryDirectory(prefix="font-weight-set-") as temp:
        work = Path(temp)
        for weight in (400, 500, 600, 700):
            target = work / f"NotoSansSC-{weight}.ttf"
            shutil.copyfile(bundled, target)
            if weight != 400:
                from fontTools.ttLib import TTFont

                font = TTFont(str(target))
                font["OS/2"].usWeightClass = weight
                font.save(str(target))
        regular = work / "NotoSansSC-400.ttf"
        manifest = {
            "file": regular.name,
            "family": "Noto Sans CJK SC",
            "source_family": "Noto Sans SC",
            "registration_family": "Noto Sans CJK SC",
            "sha256": hashlib.sha256(regular.read_bytes()).hexdigest(),
            "license": "fixture",
            "license_url": "https://example.invalid/license",
        }
        (work / "font-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        report = work / "report.json"
        checked = subprocess.run(
            [sys.executable, "scripts/validate_font_asset.py", "--font-dir", str(work), "--report", str(report), "--require-cjk", "--require-weights"],
            cwd=ROOT / "ai-ppt-editable", capture_output=True, text=True, check=False,
        )
        assert checked.returncode == 0, checked.stdout + checked.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["font_set"]["observed_weights"] == [400, 500, 600, 700], data
        assert data["font_set"]["missing_weights"] == [], data
    print("font weight set gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
