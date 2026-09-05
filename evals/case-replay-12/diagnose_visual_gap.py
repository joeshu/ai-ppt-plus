#!/usr/bin/env python3
"""Diagnose reference/candidate visual gaps without pretending diagnostics are a fidelity pass."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def resolve(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    for base in (ROOT, REPO):
        path = (base / candidate).resolve()
        if path.is_file():
            return path
    return (ROOT / candidate).resolve()


def load(path: Path, size=(960, 540)) -> np.ndarray:
    with Image.open(path).convert("RGB") as image:
        if image.size != size:
            image = image.resize(size, Image.Resampling.LANCZOS)
        return np.asarray(image, dtype=np.float32) / 255.0


def quantized_palette(array: np.ndarray, count=6) -> list[dict]:
    values = np.clip(np.rint(array.reshape(-1, 3) * 15), 0, 15).astype(np.uint8)
    packed = values[:, 0].astype(np.uint16) * 256 + values[:, 1].astype(np.uint16) * 16 + values[:, 2].astype(np.uint16)
    unique, counts = np.unique(packed, return_counts=True)
    order = np.argsort(counts)[::-1][:count]
    result = []
    total = max(1, len(packed))
    for index in order:
        code = int(unique[index])
        r, rem = divmod(code, 256)
        g, b = divmod(rem, 16)
        rgb = [round(channel / 15, 4) for channel in (r, g, b)]
        result.append({"rgb": rgb, "share": round(int(counts[index]) / total, 4)})
    return result


def edge_density(array: np.ndarray) -> float:
    gray = (array[..., 0] * .299 + array[..., 1] * .587 + array[..., 2] * .114)
    dx = np.abs(np.diff(gray, axis=1)).mean()
    dy = np.abs(np.diff(gray, axis=0)).mean()
    return round(float(dx + dy), 6)


def grid_summary(array: np.ndarray, rows=4, cols=6) -> list[dict]:
    h, w, _ = array.shape
    result = []
    for row in range(rows):
        for col in range(cols):
            y0, y1 = round(row * h / rows), round((row + 1) * h / rows)
            x0, x1 = round(col * w / cols), round((col + 1) * w / cols)
            cell = array[y0:y1, x0:x1]
            mean = cell.mean(axis=(0, 1))
            luminance = float(mean[0] * .299 + mean[1] * .587 + mean[2] * .114)
            result.append({"row": row, "col": col, "mean_rgb": [round(float(v), 4) for v in mean], "luminance": round(luminance, 4), "edge_density": edge_density(cell)})
    return result


def diagnose(reference: Path, rendered: Path) -> dict:
    ref = load(reference)
    out = load(rendered)
    diff = np.abs(ref - out)
    grid_ref = grid_summary(ref)
    grid_out = grid_summary(out)
    cells = []
    for a, b in zip(grid_ref, grid_out):
        cells.append({
            "row": a["row"], "col": a["col"],
            "rgb_mae": round(float(np.mean(np.abs(np.array(a["mean_rgb"]) - np.array(b["mean_rgb"])))), 4),
            "luminance_delta": round(abs(a["luminance"] - b["luminance"]), 4),
            "edge_density_delta": round(abs(a["edge_density"] - b["edge_density"]), 6),
            "reference": a, "candidate": b,
        })
    cells.sort(key=lambda item: (item["rgb_mae"] + item["luminance_delta"] + item["edge_density_delta"]), reverse=True)
    return {
        "mean_absolute_error": round(float(diff.mean()), 6),
        "reference_mean_rgb": [round(float(v), 4) for v in ref.mean(axis=(0, 1))],
        "candidate_mean_rgb": [round(float(v), 4) for v in out.mean(axis=(0, 1))],
        "reference_edge_density": edge_density(ref),
        "candidate_edge_density": edge_density(out),
        "reference_palette": quantized_palette(ref),
        "candidate_palette": quantized_palette(out),
        "worst_grid_cells": cells[:8],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-evaluation", default=str(ROOT / "candidate-evaluation.json"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    evaluation = json.loads(Path(args.candidate_evaluation).read_text(encoding="utf-8"))
    cases = []
    for item in evaluation.get("cases", []):
        candidate = item.get("candidate") or {}
        reference = resolve(str(candidate.get("reference") or ""))
        rendered = resolve(str(candidate.get("rendered") or ""))
        if not reference.is_file() or not rendered.is_file():
            cases.append({"case_id": item.get("case_id"), "valid": False, "missing": [name for name, path in (("reference", reference), ("rendered", rendered)) if not path.is_file()]})
            continue
        metrics = candidate.get("visual", {}).get("metrics", {})
        cases.append({
            "case_id": item.get("case_id"),
            "title": item.get("title"),
            "valid": True,
            "blurred_layout_ssim": metrics.get("blurred_layout_ssim"),
            "pixel_fidelity_score": metrics.get("pixel_fidelity_score"),
            "diagnostics": diagnose(reference, rendered),
        })
    cases.sort(key=lambda item: float(item.get("blurred_layout_ssim") or -1))
    result = {"schema": "ai-ppt-plus/12-case-visual-gap-diagnostics/v1", "case_count": len(cases), "cases": cases}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": [{"case_id": item.get("case_id"), "layout": item.get("blurred_layout_ssim"), "pixel": item.get("pixel_fidelity_score"), "reference_mean_rgb": item.get("diagnostics", {}).get("reference_mean_rgb"), "candidate_mean_rgb": item.get("diagnostics", {}).get("candidate_mean_rgb"), "worst_cells": [{"row": cell["row"], "col": cell["col"], "rgb_mae": cell["rgb_mae"]} for cell in item.get("diagnostics", {}).get("worst_grid_cells", [])[:3]]} for item in cases]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
