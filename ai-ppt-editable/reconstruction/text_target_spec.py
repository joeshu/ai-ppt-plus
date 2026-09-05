"""Build deterministic typography targets from screenshot observations.

The visual/OCR observer supplies pixel-space line evidence. This module does not
invent copy or font identity; it validates and normalizes the evidence into the
same measurement contract used by the real renderer calibration loop.
"""
from __future__ import annotations

from hashlib import sha256
from math import isfinite
from pathlib import Path
from typing import Any

SCHEMA = "ai-ppt-plus/text-target-spec/v1"


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _bbox(value: Any, width: float, height: float) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("bbox_px must contain [x, y, w, h]")
    x, y, w, h = (_finite(v, "bbox") for v in value)
    if width <= 0 or height <= 0 or w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > width + 1e-6 or y + h > height + 1e-6:
        raise ValueError("bbox_px is outside source image")
    return [x / width, y / height, w / width, h / height]


def build_text_target_spec(source_image: str | Path, observations: list[dict[str, Any]]) -> dict[str, Any]:
    source = Path(source_image)
    if not source.is_file():
        raise FileNotFoundError(source)
    from PIL import Image
    with Image.open(source) as image:
        width, height = image.size
    if width <= 0 or height <= 0:
        raise ValueError("invalid source image size")

    targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in observations:
        object_id = str(item.get("object_id") or "").strip()
        if not object_id or object_id in seen:
            raise ValueError("text observation requires unique object_id")
        seen.add(object_id)
        text = str(item.get("text") or "")
        if not text:
            raise ValueError(f"{object_id}: text is required")
        confidence = _finite(item.get("confidence", 0.0), "confidence")
        if not 0 <= confidence <= 1:
            raise ValueError(f"{object_id}: confidence must be within [0, 1]")
        bbox = _bbox(item.get("bbox_px"), float(width), float(height))
        baselines_px = item.get("baselines_px") or []
        if not isinstance(baselines_px, list) or not baselines_px:
            raise ValueError(f"{object_id}: baselines_px is required")
        baselines = [_finite(v, "baseline") / height for v in baselines_px]
        if not all(0 <= v <= 1 for v in baselines):
            raise ValueError(f"{object_id}: baseline outside source image")
        line_count = int(item.get("line_count") or len(baselines))
        if line_count != len(baselines) or line_count < 1:
            raise ValueError(f"{object_id}: line_count/baselines mismatch")
        fonts = [str(v).strip() for v in (item.get("font_candidates") or []) if str(v).strip()]
        runs = item.get("runs") or []
        if not isinstance(runs, list):
            raise ValueError(f"{object_id}: runs must be a list")
        run_text = "".join(str(run.get("text") or "") for run in runs if isinstance(run, dict))
        if runs and run_text != text:
            raise ValueError(f"{object_id}: runs must reproduce full text exactly")
        targets.append({
            "object_id": object_id,
            "text": text,
            "measurement_kind": "pdf-text-bounds",
            "ink_bbox": bbox,
            "baselines": baselines,
            "line_count": line_count,
            "font_candidates": fonts,
            "estimated_font_size_pt": item.get("estimated_font_size_pt"),
            "estimated_line_spacing": item.get("estimated_line_spacing"),
            "runs": runs,
            "confidence": confidence,
            "source_region_px": list(item.get("bbox_px")),
        })

    return {
        "schema": SCHEMA,
        "source_image": str(source),
        "source_sha256": sha256(source.read_bytes()).hexdigest(),
        "source_size_px": [width, height],
        "targets": targets,
    }
