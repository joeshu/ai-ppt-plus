#!/usr/bin/env python3
"""Smoke-test the standalone visual skill package and image-only PPTX writer."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    package = run("scripts/validate_skill_package.py", "--skill-dir", str(ROOT))
    assert package.returncode == 0, package.stdout + package.stderr
    try:
        from PIL import Image
        import pptx  # noqa: F401
    except ImportError:
        print("visual self-contained smoke: package passed; image dependencies unavailable")
        return 0
    with tempfile.TemporaryDirectory(prefix="visual-self-contained-") as temp:
        root = Path(temp)
        slides = []
        for number, color in enumerate(((18, 52, 88), (210, 64, 72)), start=1):
            image = root / f"slide-{number}.png"
            Image.new("RGB", (160, 90), color).save(image)
            slides.append({"slide_no": number, "copied_to": image.name, "canvas": {"ratio": "16:9"}})
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({"slides": slides}, ensure_ascii=False), encoding="utf-8")
        output = root / "image-slides.pptx"
        composed = run("scripts/compose_image_pptx.py", str(manifest), str(output))
        assert composed.returncode == 0, composed.stdout + composed.stderr
        with zipfile.ZipFile(output) as archive:
            slide_xml = [name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
        assert len(slide_xml) == 2, slide_xml
    print("visual self-contained smoke: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
