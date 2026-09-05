#!/usr/bin/env python3
"""Validate externally generated visual assets and bind them back to authoring decks.

The deterministic PPTX engine never generates icons/gradients/artwork itself.
This module is the strict handoff boundary: native image generation happens
outside the deterministic engine; returned assets are validated here before a
layout may resume its repair iteration.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, asdict
import hashlib
from pathlib import Path
from typing import Any


ALLOWED_BACKGROUND_MODES = {"transparent", "green", "red", "opaque", "source"}


class AssetGenerationError(ValueError):
    pass


@dataclass(frozen=True)
class GeneratedAssetResult:
    object_id: str
    file: str
    sha256: str
    width: int
    height: int
    background_mode: str
    validation: dict[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _locate(deck: dict[str, Any], object_id: str) -> tuple[str, dict[str, Any]]:
    matches: list[tuple[str, dict[str, Any]]] = []
    for slide in deck.get("slides", []) or []:
        if not isinstance(slide, dict):
            continue
        for collection in ("icons", "panels"):
            for item in slide.get(collection, []) or []:
                if not isinstance(item, dict):
                    continue
                ids = {str(v) for v in (item.get("object_id"), item.get("id"), item.get("name"), item.get("panel_id")) if v}
                if object_id in ids:
                    matches.append((collection, item))
    if not matches:
        raise AssetGenerationError(f"asset object {object_id!r} not found")
    if len(matches) > 1:
        raise AssetGenerationError(f"asset object {object_id!r} is ambiguous")
    return matches[0]


def _image_evidence(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise AssetGenerationError("Pillow is required for generated-asset validation") from exc
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            mode = image.mode
            fmt = image.format
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A")
            alpha_extrema = alpha.getextrema()
            corners = [rgba.getpixel((0, 0)), rgba.getpixel((width - 1, 0)), rgba.getpixel((0, height - 1)), rgba.getpixel((width - 1, height - 1))]
    except Exception as exc:
        raise AssetGenerationError(f"generated asset is not a readable image: {path}") from exc
    if width <= 0 or height <= 0:
        raise AssetGenerationError("generated asset dimensions must be positive")
    return {
        "format": fmt,
        "mode": mode,
        "width": width,
        "height": height,
        "alpha_min": int(alpha_extrema[0]),
        "alpha_max": int(alpha_extrema[1]),
        "corners": [list(pixel) for pixel in corners],
    }


def _is_green(pixel: list[int] | tuple[int, ...]) -> bool:
    r, g, b = pixel[:3]
    return g >= 180 and g >= r + 55 and g >= b + 55


def _is_red(pixel: list[int] | tuple[int, ...]) -> bool:
    r, g, b = pixel[:3]
    return r >= 180 and r >= g + 55 and r >= b + 55


def validate_generated_asset(request: dict[str, Any], response: dict[str, Any], *, base_dir: Path | None = None) -> GeneratedAssetResult:
    object_id = str(request.get("object_id") or "").strip()
    if not object_id:
        raise AssetGenerationError("generation request object_id is required")
    if str(response.get("object_id") or "").strip() != object_id:
        raise AssetGenerationError("generated asset object_id does not match request")
    expected_mode = str(request.get("background_mode") or "transparent")
    actual_mode = str(response.get("background_mode") or expected_mode)
    if expected_mode not in ALLOWED_BACKGROUND_MODES or actual_mode not in ALLOWED_BACKGROUND_MODES:
        raise AssetGenerationError("unsupported generated asset background_mode")
    if actual_mode != expected_mode:
        raise AssetGenerationError(f"generated asset background_mode mismatch: expected {expected_mode}, got {actual_mode}")

    raw_file = response.get("file")
    if not isinstance(raw_file, str) or not raw_file:
        raise AssetGenerationError("generated asset response file is required")
    path = Path(raw_file)
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    path = path.resolve()
    if not path.is_file():
        raise AssetGenerationError(f"generated asset file does not exist: {path}")

    evidence = _image_evidence(path)
    if evidence["format"] != "PNG":
        raise AssetGenerationError("generated asset must be PNG at the deterministic handoff boundary")

    corners = evidence["corners"]
    if expected_mode == "transparent" and evidence["alpha_min"] >= 250:
        raise AssetGenerationError("transparent asset has no meaningful alpha transparency")
    if expected_mode == "green" and not all(_is_green(pixel) for pixel in corners):
        raise AssetGenerationError("green-background asset does not have green key-color corners")
    if expected_mode == "red" and not all(_is_red(pixel) for pixel in corners):
        raise AssetGenerationError("red-background asset does not have red key-color corners")

    digest = _sha256(path)
    declared = response.get("sha256")
    if declared not in (None, "") and str(declared).lower() != digest:
        raise AssetGenerationError("generated asset sha256 does not match file bytes")

    return GeneratedAssetResult(
        object_id=object_id,
        file=str(path),
        sha256=digest,
        width=int(evidence["width"]),
        height=int(evidence["height"]),
        background_mode=expected_mode,
        validation=evidence,
    )


def bind_generated_asset(deck: dict[str, Any], request: dict[str, Any], result: GeneratedAssetResult) -> dict[str, Any]:
    """Bind a validated generated asset without changing requested geometry."""
    repaired = deepcopy(deck)
    _, item = _locate(repaired, result.object_id)
    preserved_before = {key: item.get(key) for key in ("x", "y", "w", "h", "rotation") if key in item}
    expected_geometry = dict(request.get("preserve_geometry") or {})
    for key, expected in expected_geometry.items():
        if key in preserved_before and preserved_before[key] != expected:
            raise AssetGenerationError(f"asset geometry changed before bind for {key}")
    item["file"] = result.file
    item["source_sha256"] = result.sha256
    item["background_mode"] = result.background_mode
    item["generation_provenance"] = {
        "kind": "native_image_generation",
        "finding_id": request.get("finding_id"),
        "generation_prompt": request.get("generation_prompt"),
        "sha256": result.sha256,
        "width": result.width,
        "height": result.height,
    }
    preserved_after = {key: item.get(key) for key in preserved_before}
    if preserved_after != preserved_before:
        raise AssetGenerationError("asset bind mutated placement geometry")
    return {
        "deck": repaired,
        "report": {
            "schema": "ai-ppt-plus/generated-asset-bind/v1",
            "valid": True,
            "object_id": result.object_id,
            "asset": asdict(result),
            "preserved_geometry": preserved_after,
        },
    }
