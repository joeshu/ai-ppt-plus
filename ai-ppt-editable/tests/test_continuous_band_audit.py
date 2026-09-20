#!/usr/bin/env python3
from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from scripts.audit_continuous_band import audit


def _band(path: Path, offset: int) -> None:
    image = Image.new("RGB", (200, 100), "white")
    draw = ImageDraw.Draw(image)
    points = [(0, 72 + offset), (50, 62 + offset), (100, 70 + offset), (150, 55 + offset), (199, 65 + offset), (199, 99), (0, 99)]
    draw.polygon(points, fill=(210, 0, 35))
    image.save(path)


def test_contour_landmarks_detect_shape_shift() -> None:
    with tempfile.TemporaryDirectory(prefix="contour-audit-") as folder:
        root = Path(folder)
        reference = root / "reference.png"
        candidate = root / "candidate.png"
        _band(reference, 0)
        _band(candidate, -10)
        report = audit(reference, candidate, [0, 0.4, 1, 0.6], 9, "red")
        assert report["valid"] is True
        assert report["comparison"]["resolved_count"] == 9
        assert report["comparison"]["mean_absolute_delta_region_norm"] > 0.1
