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


def test_full_bleed_footer_rejects_uncovered_bottom_edge() -> None:
    with tempfile.TemporaryDirectory(prefix="contour-edge-") as folder:
        root = Path(folder)
        reference, candidate = root / "reference.png", root / "candidate.png"
        _band(reference, 0)
        _band(candidate, 0)
        image = Image.open(candidate)
        ImageDraw.Draw(image).rectangle((0, 90, 199, 99), fill="white")
        image.save(candidate)
        failed = audit(reference, candidate, [0, 0.4, 1, 0.6], 9, "red", True)
        assert not failed["valid"]
        edge = failed["comparison"]["bottom_edge_continuity"]
        assert edge["applicable"] and not edge["passed"]
        _band(candidate, 0)
        passed = audit(reference, candidate, [0, 0.4, 1, 0.6], 9, "red", True)
        assert passed["valid"]
