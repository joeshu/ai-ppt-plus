#!/usr/bin/env python3
"""Create final/reference visual QA evidence and region-level diagnostics."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from atomic_output import atomic_write_json


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_map(path: str | None, default):
    if not path: return default
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalize(source: Image.Image, size: tuple[int, int]) -> Image.Image:
    return source.convert("RGB").resize(size, Image.Resampling.LANCZOS)


def stats(image: Image.Image) -> dict:
    rgb = image.convert("RGB")
    stat = ImageStat.Stat(rgb)
    spread = sum(stat.var) ** 0.5
    return {"mean": [round(v, 4) for v in stat.mean], "stddev": [round(v, 4) for v in stat.stddev], "nonuniform": spread > 2.0}


def bbox(region):
    if isinstance(region, dict):
        if "bbox" in region: return tuple(int(v) for v in region["bbox"])
        if all(k in region for k in ("left", "top", "width", "height")): return tuple(int(region[k]) for k in ("left", "top", "width", "height"))
    return tuple(int(v) for v in region)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", action="append", required=True)
    parser.add_argument("--render", action="append", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--regions")
    parser.add_argument("--anchors")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    out_dir = Path(args.output_dir).resolve(); out_dir.mkdir(parents=True, exist_ok=True)
    references = [Path(p).resolve() for p in args.reference]
    renders = [Path(p).resolve() for p in args.render]
    issues = []
    if len(references) != len(renders): issues.append({"severity": "blocker", "code": "page_count_mismatch", "references": len(references), "renders": len(renders)})
    region_data = load_map(args.regions, {})
    anchor_data = load_map(args.anchors, {})
    pages = []
    for index, (ref_path, render_path) in enumerate(zip(references, renders), start=1):
        if not ref_path.is_file() or not render_path.is_file():
            issues.append({"severity": "blocker", "code": "visual_input_missing", "page": index}); continue
        with Image.open(render_path) as render_image, Image.open(ref_path) as ref_image:
            render = render_image.convert("RGB")
            reference = normalize(ref_image, render.size)
            if render.width / render.height < 1.7 or render.width / render.height > 1.82:
                issues.append({"severity": "blocker", "code": "render_ratio_invalid", "page": index, "size": render.size})
            diff = ImageChops.difference(reference, render)
            overlay = Image.blend(reference, render, 0.5)
            side = Image.new("RGB", (render.width * 2, render.height), "white")
            side.paste(reference, (0, 0)); side.paste(render, (render.width, 0))
            names = {"reference": out_dir / f"slide-{index}-reference.png", "final": out_dir / f"slide-{index}-final.png",
                     "side_by_side": out_dir / f"slide-{index}-reference-vs-final.png", "overlay": out_dir / f"slide-{index}-overlay.png",
                     "diff": out_dir / f"slide-{index}-absolute-diff.png"}
            reference.save(names["reference"]); render.save(names["final"]); side.save(names["side_by_side"]); overlay.save(names["overlay"]); diff.save(names["diff"])
            diff_stat = ImageStat.Stat(diff)
            page = {"page": index, "size": {"width": render.width, "height": render.height},
                    "reference": {"path": str(names["reference"]), "sha256": sha256(names["reference"])},
                    "final": {"path": str(names["final"]), "sha256": sha256(names["final"]), "stats": stats(render)},
                    "side_by_side": str(names["side_by_side"]), "overlay": str(names["overlay"]), "diff": str(names["diff"]),
                    "difference": {"mean_abs": round(sum(diff_stat.mean) / 3 / 255, 6), "rmse": round(math.sqrt(sum(v * v for v in diff_stat.mean)) / 3 / 255, 6)},
                    "regions": [], "anchors": anchor_data.get(str(index), anchor_data.get(index, []))}
            page_regions = region_data.get(str(index), region_data.get(index, [])) if isinstance(region_data, dict) else []
            if isinstance(page_regions, dict): page_regions = [{"name": key, **(value if isinstance(value, dict) else {"bbox": value})} for key, value in page_regions.items()]
            for region in page_regions:
                try:
                    left, top, width, height = bbox(region); crop_box = (left, top, left + width, top + height)
                    name = str(region.get("name", f"region-{len(page['regions']) + 1}")) if isinstance(region, dict) else f"region-{len(page['regions']) + 1}"
                    crop_side = Image.new("RGB", (width * 2, height), "white"); crop_side.paste(reference.crop(crop_box), (0, 0)); crop_side.paste(render.crop(crop_box), (width, 0))
                    crop_diff = diff.crop(crop_box)
                    side_path = out_dir / f"slide-{index}-{name}-reference-vs-final.png"; diff_path = out_dir / f"slide-{index}-{name}-diff.png"
                    crop_side.save(side_path); crop_diff.save(diff_path)
                    page["regions"].append({"name": name, "bbox": [left, top, width, height], "side_by_side": str(side_path), "diff": str(diff_path), "difference": stats(crop_diff)})
                except Exception as exc:
                    issues.append({"severity": "blocker", "code": "region_crop_failed", "page": index, "message": str(exc)})
            if args.strict and not page["regions"]:
                issues.append({"severity": "blocker", "code": "regions_missing", "page": index})
            pages.append(page)
    result = {"schema": "ai-ppt-plus/visual-qa-bundle/v1", "valid": not issues, "status": "passed" if not issues else "blocked", "strict": args.strict,
              "output_dir": str(out_dir), "page_count": len(pages), "pages": pages, "region_manifest": str(Path(args.regions).resolve()) if args.regions else None,
              "anchor_manifest": str(Path(args.anchors).resolve()) if args.anchors else None, "issues": issues,
              "rule": "Visual similarity is diagnostic; normalized same-size comparisons and human inspection of required regions remain mandatory."}
    atomic_write_json(Path(args.report).resolve(), result); print(json.dumps(result, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__": raise SystemExit(main())
