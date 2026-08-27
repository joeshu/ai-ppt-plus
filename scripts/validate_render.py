#!/usr/bin/env python3
"""Run deterministic non-blank and key-region checks on rendered pages.

This gate catches blank pages and visibly empty critical regions, but it does
not replace human visual review or OCR/content verification.

Usage: validate_render.py RENDER_DIR --expected-pages N
       [--region name=x,y,w,h ...] [--report REPORT.json]
Exit 0 when mechanical checks pass, 2 when a gate fails, 3 on runtime error.
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageStat


def region_spec(value):
    try:
        name, coords = value.split("=", 1)
        x, y, w, h = (int(part) for part in coords.split(","))
        if not name or min(w, h) <= 0 or min(x, y) < 0:
            raise ValueError
        return name, (x, y, w, h)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("region must be name=x,y,w,h") from exc


def image_stats(image):
    gray = image.convert("L")
    stat = ImageStat.Stat(gray)
    mean, std = stat.mean[0], stat.stddev[0]
    extrema = gray.getextrema()
    return {"mean": round(mean, 3), "stddev": round(std, 3), "min": extrema[0], "max": extrema[1], "nonuniform": std >= 2.0 and extrema[1] - extrema[0] >= 8}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("render_dir")
    parser.add_argument("--expected-pages", type=int, required=True)
    parser.add_argument("--region", action="append", type=region_spec, default=[])
    parser.add_argument("--report")
    args = parser.parse_args()
    render_dir = Path(args.render_dir)
    pages = sorted(render_dir.glob("slide-*.png"), key=lambda path: int(path.stem.split("-")[-1])) if render_dir.is_dir() else []
    issues = []
    if len(pages) != args.expected_pages:
        issues.append({"severity": "blocker", "code": "page_count_mismatch", "expected": args.expected_pages, "observed": len(pages)})
    page_results = []
    for page in pages:
        try:
            with Image.open(page) as image:
                image.load()
                result = {"page": page.name, "width": image.width, "height": image.height, "stats": image_stats(image), "regions": []}
                if image.width < 320 or image.height < 180:
                    issues.append({"severity": "blocker", "code": "render_too_small", "page": page.name})
                if not result["stats"]["nonuniform"]:
                    issues.append({"severity": "blocker", "code": "blank_or_uniform_page", "page": page.name})
                for name, (x, y, w, h) in args.region:
                    if x + w > image.width or y + h > image.height:
                        issues.append({"severity": "blocker", "code": "region_out_of_bounds", "page": page.name, "region": name})
                        continue
                    stats = image_stats(image.crop((x, y, x + w, y + h)))
                    result["regions"].append({"name": name, "bbox": [x, y, w, h], "stats": stats})
                    if not stats["nonuniform"]:
                        issues.append({"severity": "blocker", "code": "blank_key_region", "page": page.name, "region": name})
                page_results.append(result)
        except Exception as exc:
            issues.append({"severity": "blocker", "code": "render_read_error", "page": page.name, "message": f"{type(exc).__name__}: {exc}"})
    result = {"schema": "ai-ppt-plus/render-visual-gate/v1", "valid": not any(item["severity"] == "blocker" for item in issues), "render_dir": str(render_dir.resolve()), "expected_pages": args.expected_pages, "pages": page_results, "issues": issues, "human_visual_review_required": True, "limitation": "non-blank checks do not prove semantic text correctness or reference fidelity"}
    if args.report:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
