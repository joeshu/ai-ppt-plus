#!/usr/bin/env python3
"""Regression tests for generated-page OCR and emphasis readback."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("visual assertions: skipped (Pillow unavailable)")
        return 0

    with tempfile.TemporaryDirectory(prefix="visual-assertions-") as temp:
        root = Path(temp)
        image = root / "slide-1.png"
        canvas = Image.new("RGB", (800, 450), "white")
        draw = ImageDraw.Draw(canvas)
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        font = ImageFont.truetype(font_path, 42) if Path(font_path).is_file() else None
        draw.text((40, 40), "REAL TEXT", fill="#F28C28", font=font)
        canvas.save(image)
        plan = root / "plan.json"
        write_json(plan, {
            "schema": "ai-ppt-plus/visual-generation-plan/v1",
            "project_id": "visual-assertion-fixture",
            "slides": [{
                "slide_no": 1,
                "visual_assertions": {
                    "ocr_lang": "eng",
                    "must_contain_text": ["REAL TEXT"],
                    "forbidden_text": ["PLACEHOLDER"],
                    "min_ink_ratio": 0.001,
                    "keyword_emphasis": [{
                        "text": "REAL TEXT",
                        "color": "#F28C28",
                        "min_pixels": 20,
                        "tolerance": 3,
                        "region": [0, 0, 0.5, 0.4],
                    }],
                },
            }],
        })
        manifest = root / "manifest.json"
        write_json(manifest, {"slides": [{"slide_no": 1, "copied_to": image.name}]})
        report = root / "report.json"
        command = [
            sys.executable, "scripts/validate_visual_assertions.py", str(plan),
            "--manifest", str(manifest), "--expected-pages", "1", "--report", str(report),
        ]
        valid = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert valid.returncode == 0, valid.stdout + valid.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["valid"] is True
        assert data["evidence"]["slides"][0]["keyword_emphasis"][0]["passed"] is True, data
        assert data["evidence"]["slides"][0]["keyword_emphasis"][0]["text_readback"]["passed"] is True, data

        color_only = root / "color-only.png"
        color_canvas = Image.new("RGB", (800, 450), "white")
        ImageDraw.Draw(color_canvas).rectangle((40, 40, 300, 100), fill="#F28C28")
        color_canvas.save(color_only)
        color_manifest = root / "color-only-manifest.json"
        color_manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
        color_manifest_data["slides"][0]["copied_to"] = color_only.name
        write_json(color_manifest, color_manifest_data)
        color_check = subprocess.run([
            sys.executable, "scripts/validate_visual_assertions.py", str(plan),
            "--manifest", str(color_manifest), "--expected-pages", "1",
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        assert color_check.returncode == 2 and "visual_keyword_text_missing" in color_check.stdout, color_check.stdout

        broken = json.loads(plan.read_text(encoding="utf-8"))
        broken["slides"][0]["visual_assertions"]["must_contain_text"] = ["MISSING TEXT"]
        write_json(plan, broken)
        failed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert failed.returncode == 2 and "visual_text_missing" in failed.stdout, failed.stdout

        fallback = json.loads(plan.read_text(encoding="utf-8"))
        fallback["slides"][0]["visual_assertions"]["ocr_lang"] = "chi_sim+eng"
        fallback["slides"][0]["visual_assertions"]["ocr_failure_policy"] = "manual-review"
        fallback["slides"][0]["visual_assertions"]["must_contain_text"] = ["中文回读"]
        write_json(plan, fallback)
        review = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert review.returncode == 0, review.stdout + review.stderr
        review_data = json.loads(review.stdout)
        assert review_data["status"] == "needs-human-review", review_data
        assert any(item["code"] == "visual_ocr_manual_review_required" for item in review_data["issues"]), review_data

        fallback["slides"][0]["visual_assertions"]["ocr_failure_policy"] = "block"
        write_json(plan, fallback)
        strict = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert strict.returncode == 2 and "visual_ocr_unavailable" in strict.stdout, strict.stdout

    print("visual assertion readback: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
