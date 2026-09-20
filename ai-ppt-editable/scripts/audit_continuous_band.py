#!/usr/bin/env python3
"""Compare a continuous footer/header color-band contour in two renders.

This diagnostic catches a class of failures that rectangular bbox checks miss:
the band occupies the correct box but its wave, funnel or ribbon profile is
wrong.  It emits sampled top-edge landmarks and never invents a universal
release threshold.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _rgb_mask(pixel: tuple[int, ...], mode: str) -> bool:
    r, g, b = pixel[:3]
    if mode == "red":
        return r >= 130 and r >= g * 1.35 and r >= b * 1.18 and (r - min(g, b)) >= 38
    raise ValueError(f"unsupported mask mode: {mode}")


def _profile(path: Path, region: list[float], samples: int, mode: str) -> dict:
    from PIL import Image
    import numpy as np

    with Image.open(path) as source:
        image = source.convert("RGB")
        image.load()
    left = max(0, round(region[0] * image.width))
    top = max(0, round(region[1] * image.height))
    right = min(image.width, round((region[0] + region[2]) * image.width))
    bottom = min(image.height, round((region[1] + region[3]) * image.height))
    if right <= left or bottom <= top:
        raise ValueError("region is empty")
    crop = np.asarray(image)[top:bottom, left:right]
    red = crop[:, :, 0].astype(np.int16)
    green = crop[:, :, 1].astype(np.int16)
    blue = crop[:, :, 2].astype(np.int16)
    if mode == "red":
        mask = ((red >= 130) & (red >= green * 1.35) & (red >= blue * 1.18) & ((red - np.minimum(green, blue)) >= 38)).astype("uint8")
    else:
        raise ValueError(f"unsupported mask mode: {mode}")
    if not mask.any():
        raise ValueError("no continuous color band detected")
    points = []
    for index in range(samples):
        fraction = index / (samples - 1)
        local_x = min(right - left - 1, round(fraction * (right - left - 1)))
        x = left + local_x
        strip = mask[:, max(0, local_x - 2):min(mask.shape[1], local_x + 3)]
        active = strip.mean(axis=1) >= 0.4
        hits = np.where(active)[0]
        runs = []
        if hits.size:
            start = previous = int(hits[0])
            for value in hits[1:]:
                value = int(value)
                if value != previous + 1:
                    runs.append((start, previous))
                    start = value
                previous = value
            runs.append((start, previous))
        substantial = [run for run in runs if run[1] - run[0] + 1 >= 3]
        chosen = max(substantial, key=lambda run: run[1]) if substantial else None
        y = top + chosen[0] if chosen else None
        points.append({
            "x_fraction": round(fraction, 6),
            "x_px": x,
            "top_y_px": y,
            "top_y_region_norm": round((y - top) / (bottom - top), 6) if y is not None else None,
        })
    return {"path": str(path.resolve()), "size_px": list(image.size), "region_px": [left, top, right, bottom], "landmarks": points}


def audit(reference: Path, candidate: Path, region: list[float], samples: int, mode: str) -> dict:
    ref = _profile(reference, region, samples, mode)
    cand = _profile(candidate, region, samples, mode)
    deltas = []
    unresolved = []
    for r, c in zip(ref["landmarks"], cand["landmarks"]):
        if r["top_y_region_norm"] is None or c["top_y_region_norm"] is None:
            unresolved.append(r["x_fraction"])
            continue
        deltas.append({
            "x_fraction": r["x_fraction"],
            "reference_y_norm": r["top_y_region_norm"],
            "candidate_y_norm": c["top_y_region_norm"],
            "delta_region_norm": round(c["top_y_region_norm"] - r["top_y_region_norm"], 6),
        })
    absolute = [abs(row["delta_region_norm"]) for row in deltas]
    return {
        "schema": "ai-ppt-plus/continuous-band-contour/v1",
        "valid": bool(deltas) and not unresolved,
        "mask_mode": mode,
        "region_norm": region,
        "reference": ref,
        "candidate": cand,
        "comparison": {
            "sample_count": samples,
            "resolved_count": len(deltas),
            "unresolved_x_fractions": unresolved,
            "mean_absolute_delta_region_norm": round(sum(absolute) / len(absolute), 6) if absolute else None,
            "max_absolute_delta_region_norm": round(max(absolute), 6) if absolute else None,
            "landmark_deltas": deltas,
        },
        "review": "diagnostic: inspect material contour differences in the composed local crop; no universal numeric release threshold",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--region", nargs=4, type=float, default=[0.0, 0.78, 1.0, 0.22], metavar=("X", "Y", "W", "H"))
    parser.add_argument("--samples", type=int, default=13)
    parser.add_argument("--mask-mode", choices=["red"], default="red")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.samples < 5:
        raise SystemExit("--samples must be at least 5")
    report = audit(args.reference.resolve(), args.candidate.resolve(), list(args.region), args.samples, args.mask_mode)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload + "\n", encoding="utf-8")
    if args.json or not args.report:
        print(payload)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
