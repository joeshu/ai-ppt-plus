#!/usr/bin/env python3
"""Normalize viewer captures before slide-image comparison.

WPS/PowerPoint screenshots often include dark letterbox bars outside the
slide.  Treating those pixels as slide content creates false aspect-ratio and
visual-diff regressions.  This module deliberately detects only strong,
contiguous edge bars whose remaining viewport has a plausible presentation
ratio; ordinary dark slide artwork is left untouched.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


DEFAULT_DARK_THRESHOLD = 40
DEFAULT_DARK_FRACTION = 0.90
DEFAULT_MIN_BAR_FRACTION = 0.01
DEFAULT_MAX_BAR_FRACTION = 0.45
DEFAULT_RATIO_TOLERANCE = 0.035


def _edge_fractions(image, dark_threshold: int) -> tuple[list[float], list[float], tuple[int, int]]:
    """Return dark-pixel fractions for columns and rows of a small sample."""
    max_dimension = 1400
    sample = image
    if max(image.size) > max_dimension:
        scale = max_dimension / max(image.size)
        sample = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        )

    try:
        import numpy as np

        pixels = np.asarray(sample, dtype=np.uint8)
        dark = pixels.max(axis=2) <= dark_threshold
        return dark.mean(axis=0).tolist(), dark.mean(axis=1).tolist(), sample.size
    except ImportError:
        # Pillow is the only required image dependency.  The fallback is used
        # only when numpy is unavailable and operates on the bounded sample.
        pixels = list(sample.getdata())
        width, height = sample.size
        columns = [0] * width
        rows = [0] * height
        for index, (red, green, blue) in enumerate(pixels):
            if max(red, green, blue) <= dark_threshold:
                columns[index % width] += 1
                rows[index // width] += 1
        return (
            [value / max(1, height) for value in columns],
            [value / max(1, width) for value in rows],
            sample.size,
        )


def _leading_run(values: list[float], threshold: float) -> int:
    count = 0
    for value in values:
        if value < threshold:
            break
        count += 1
    return count


def _trailing_run(values: list[float], threshold: float) -> int:
    count = 0
    for value in reversed(values):
        if value < threshold:
            break
        count += 1
    return count


def _empty_metadata(width: int, height: int, reason: str, **extra: Any) -> dict[str, Any]:
    ratio = width / height if height else None
    result: dict[str, Any] = {
        "detected": False,
        "crop_box": [0, 0, width, height],
        "original_size": [width, height],
        "content_size": [width, height],
        "original_ratio": round(ratio, 7) if ratio is not None else None,
        "content_ratio": round(ratio, 7) if ratio is not None else None,
        "bar_pixels": {"left": 0, "top": 0, "right": 0, "bottom": 0},
        "confidence": 0.0,
        "reason": reason,
        "artifact_classification": "none",
    }
    result.update(extra)
    return result


def detect_viewer_crop(
    image,
    expected_ratio: float | None = None,
    *,
    dark_threshold: int = DEFAULT_DARK_THRESHOLD,
    dark_fraction: float = DEFAULT_DARK_FRACTION,
    min_bar_fraction: float = DEFAULT_MIN_BAR_FRACTION,
    max_bar_fraction: float = DEFAULT_MAX_BAR_FRACTION,
    ratio_tolerance: float = DEFAULT_RATIO_TOLERANCE,
) -> dict[str, Any]:
    """Detect a strong edge letterbox and return a pixel crop proposal.

    ``expected_ratio`` is preferred when the deck ratio is known.  When it is
    omitted, the remaining viewport must still be within a conservative
    presentation range.  The result is metadata-only; callers decide whether
    to apply ``crop_box``.
    """
    width, height = image.size
    if width < 2 or height < 2:
        return _empty_metadata(width, height, "image_too_small")

    rgb = image.convert("RGB")
    column_fraction, row_fraction, sample_size = _edge_fractions(rgb, dark_threshold)
    sample_width, sample_height = sample_size
    left = round(_leading_run(column_fraction, dark_fraction) * width / sample_width)
    right = round(_trailing_run(column_fraction, dark_fraction) * width / sample_width)
    top = round(_leading_run(row_fraction, dark_fraction) * height / sample_height)
    bottom = round(_trailing_run(row_fraction, dark_fraction) * height / sample_height)

    min_x = max(4, round(width * min_bar_fraction))
    min_y = max(4, round(height * min_bar_fraction))
    max_x = round(width * max_bar_fraction)
    max_y = round(height * max_bar_fraction)
    if left < min_x:
        left = 0
    if right < min_x:
        right = 0
    if top < min_y:
        top = 0
    if bottom < min_y:
        bottom = 0
    left = min(left, max_x)
    right = min(right, max_x)
    top = min(top, max_y)
    bottom = min(bottom, max_y)

    content_width = width - left - right
    content_height = height - top - bottom
    if content_width < max(2, round(width * 0.50)) or content_height < max(2, round(height * 0.50)):
        return _empty_metadata(width, height, "no_safe_viewport", edge_fractions={"columns": column_fraction[:2] + column_fraction[-2:], "rows": row_fraction[:2] + row_fraction[-2:]})
    if left == right == top == bottom == 0:
        return _empty_metadata(width, height, "no_contiguous_dark_edge_bar")

    content_ratio = content_width / content_height if content_height else 0.0
    if expected_ratio and expected_ratio > 0:
        allowed = max(ratio_tolerance, expected_ratio * 0.025)
        if abs(content_ratio - expected_ratio) > allowed:
            return _empty_metadata(
                width,
                height,
                "viewport_ratio_not_expected",
                candidate_content_ratio=round(content_ratio, 7),
                expected_ratio=expected_ratio,
            )
    elif not 0.75 <= content_ratio <= 2.50:
        return _empty_metadata(
            width,
            height,
            "viewport_ratio_not_presentation_like",
            candidate_content_ratio=round(content_ratio, 7),
        )

    # A genuine dark slide may have dark outer artwork.  Reject a proposal if
    # the first content band remains overwhelmingly dark on every edge; viewer
    # bars have a clear transition into the slide viewport.
    sample_x = max(1, round(width * 0.005))
    sample_y = max(1, round(height * 0.005))
    inner_box = rgb.crop((left, top, width - right, height - bottom))
    inner_columns, inner_rows, inner_sample_size = _edge_fractions(inner_box, dark_threshold)
    inner_sample_width, inner_sample_height = inner_sample_size
    sample_inner_x = max(1, round(sample_x * inner_sample_width / max(1, inner_box.width)))
    sample_inner_y = max(1, round(sample_y * inner_sample_height / max(1, inner_box.height)))
    inner_edges = [
        inner_columns[:sample_inner_x],
        inner_columns[-sample_inner_x:],
        inner_rows[:sample_inner_y],
        inner_rows[-sample_inner_y:],
    ]
    if all(edge and sum(edge) / len(edge) >= 0.80 for edge in inner_edges):
        return _empty_metadata(width, height, "inner_viewport_still_dark")

    bar_count = sum(value > 0 for value in (left, right, top, bottom))
    strongest_bar = max(left / width, right / width, top / height, bottom / height)
    confidence = min(1.0, 0.55 + 0.12 * bar_count + min(0.25, strongest_bar))
    crop_box = [left, top, width - right, height - bottom]
    return {
        "detected": True,
        "crop_box": crop_box,
        "original_size": [width, height],
        "content_size": [content_width, content_height],
        "original_ratio": round(width / height, 7) if height else None,
        "content_ratio": round(content_ratio, 7),
        "bar_pixels": {"left": left, "top": top, "right": right, "bottom": bottom},
        "confidence": round(confidence, 4),
        "expected_ratio": expected_ratio,
        "dark_threshold": dark_threshold,
        "dark_fraction_threshold": dark_fraction,
        "reason": "strong_contiguous_edge_bars",
        "artifact_classification": "viewer_only_capture_chrome",
        "raw_capture_preserved": True,
    }


def load_viewport(path: str | Path, expected_ratio: float | None = None):
    """Load an RGB image and apply a validated viewer crop proposal."""
    from PIL import Image

    source_path = Path(path)
    with Image.open(source_path) as image:
        rgb = image.convert("RGB")
        metadata = detect_viewer_crop(rgb, expected_ratio=expected_ratio)
        if metadata["detected"]:
            rgb = rgb.crop(tuple(metadata["crop_box"]))
        return rgb, metadata
