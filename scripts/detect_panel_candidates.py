#!/usr/bin/env python3
"""Detect candidate rectangular content panels without mutating a layout.

This is a conservative proposal tool, not an auto-cropper. It uses image
edge projections to propose a regular row/column grid, then writes
``needs-human-confirmation`` so a reviewer can correct boundaries before
``extract_panels.py`` is called.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def groups(values: np.ndarray, threshold: float, gap: int = 3):
    indexes = np.where(values >= threshold)[0]
    if not len(indexes):
        return []
    out, start, prev = [], int(indexes[0]), int(indexes[0])
    for value in indexes[1:]:
        value = int(value)
        if value - prev > gap:
            out.append((start, prev))
            start = value
        prev = value
    out.append((start, prev))
    return out


def peaks(profile: np.ndarray, count: int, margin: int = 4):
    # Non-maximum suppression keeps projections from returning the same line
    # repeatedly. The fallback is evenly spaced, but remains low-confidence.
    work = profile.copy()
    found = []
    for _ in range(max(0, count)):
        i = int(work.argmax())
        if work[i] <= 0:
            break
        found.append(i)
        work[max(0, i - margin): min(len(work), i + margin + 1)] = 0
    return sorted(found)


def _boundary_centers(profile: np.ndarray, expected: int | None, size: int):
    """Return boundary candidates without inventing a grid when no hint exists."""
    if expected is not None:
        return peaks(profile, expected + 1, max(4, size // 10))
    # Unconstrained mode is deliberately conservative: discover prominent
    # boundaries, but do not fill the slide with an assumed 2x3 grid.
    return peaks(profile, min(8, max(2, size // 180)), max(4, size // 14))


def detect(image_path: str, rows: int | None, cols: int | None, min_area: float):
    if rows is not None and rows < 1:
        raise ValueError("--rows must be >= 1")
    if cols is not None and cols < 1:
        raise ValueError("--cols must be >= 1")
    with Image.open(image_path) as image:
        original_w, original_h = image.size
        scale = min(1.0, 1400.0 / max(original_w, original_h))
        w, h = max(1, round(original_w * scale)), max(1, round(original_h * scale))
        rgb = np.asarray(image.convert("RGB").resize((w, h)), dtype=np.float32)
    gray = rgb.mean(axis=2)
    edge = np.zeros_like(gray)
    edge[1:, :] += np.abs(gray[1:, :] - gray[:-1, :])
    edge[:, 1:] += np.abs(gray[:, 1:] - gray[:, :-1])
    edge = np.clip(edge, 0, 255)
    horizontal = (edge.mean(axis=1) + (edge > 28).mean(axis=1) * 40)
    vertical = (edge.mean(axis=0) + (edge > 28).mean(axis=0) * 40)
    # A line is more likely to be a panel boundary when it remains active over
    # a substantial fraction of the perpendicular dimension.
    row_groups = groups(horizontal, np.percentile(horizontal, 78), gap=max(2, h // 220))
    col_groups = groups(vertical, np.percentile(vertical, 78), gap=max(2, w // 220))
    row_centers = [int((a + b) / 2) for a, b in row_groups]
    col_centers = [int((a + b) / 2) for a, b in col_groups]
    row_centers = _boundary_centers(horizontal, rows, h)
    col_centers = _boundary_centers(vertical, cols, w)
    row_centers = sorted(set(max(0, min(h - 1, x)) for x in row_centers))
    col_centers = sorted(set(max(0, min(w - 1, x)) for x in col_centers))
    candidates = []
    for r in range(len(row_centers) - 1):
        for c in range(len(col_centers) - 1):
            x0, x1 = col_centers[c], col_centers[c + 1]
            y0, y1 = row_centers[r], row_centers[r + 1]
            area = (x1 - x0) * (y1 - y0)
            if area / (w * h) < min_area:
                continue
            candidates.append({"candidate_id": f"panel-{len(candidates)+1:02d}", "source_bbox": [round(x0 / scale), round(y0 / scale), round((x1 - x0) / scale), round((y1 - y0) / scale)], "row": r + 1, "column": c + 1, "confidence": round(0.66 if rows is not None and cols is not None else 0.40, 2), "boundary_evidence": {"horizontal_profile_peak": round(float(horizontal[y0:y1].max()), 2), "vertical_profile_peak": round(float(vertical[x0:x1].max()), 2)}})
    return {"schema": "ai-ppt-plus/panel-candidates/v1", "source": str(Path(image_path).resolve()), "source_size": [original_w, original_h], "analysis_size": [w, h], "inference": {"rows": len(row_centers) - 1, "columns": len(col_centers) - 1, "rows_hint": rows, "columns_hint": cols, "used_assumed_grid": False}, "status": "needs-human-confirmation", "candidates": candidates, "human_review": ["confirm the detected count and whether the layout is actually a repeated-panel structure", "correct each source_bbox against visible panel borders", "exclude Logo, footer, intro bar and decorative gradients", "only then pass approved bboxes to extract_panels.py"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image")
    ap.add_argument("--rows", type=int)
    ap.add_argument("--cols", type=int)
    ap.add_argument("--min-area", type=float, default=0.015)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    try:
        result = detect(args.image, args.rows, args.cols, args.min_area)
    except ValueError as exc:
        ap.error(str(exc))
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": True, "status": result["status"], "candidates": len(result["candidates"]), "output": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
