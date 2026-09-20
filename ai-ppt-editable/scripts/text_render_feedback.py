#!/usr/bin/env python3
"""Compare planned native text against fresh reference/candidate render crops.

This is a diagnostic feedback loop, not a scalar visual release gate. It binds
TextFit evidence and AuthoringPlan ownership to same-coordinate render crops,
then emits object-scoped position/scale/hierarchy diagnostics for targeted
repair.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

SCHEMA = "ai-ppt-plus/text-render-feedback/v1"
DEFAULT_POSITION_TOLERANCE_PX = 3.0
DEFAULT_SCALE_TOLERANCE = 0.10
DEFAULT_COVERAGE_TOLERANCE = 0.10


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_id(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "text")).strip("._") or "text"


def _object_index(plan: dict) -> dict[str, dict]:
    return {
        str(row["object_id"]): row
        for row in (plan.get("objects") or [])
        if isinstance(row, dict) and isinstance(row.get("object_id"), str) and row.get("object_id")
    }


def _owner_candidates(slot_id: str) -> list[str]:
    parts = slot_id.split(":")
    values = [slot_id]
    if parts and parts[0] in {"text", "shape"} and len(parts) >= 2:
        values.append(":".join(parts[1:]))
    elif parts and parts[0] in {"table", "chart"} and len(parts) >= 2:
        values.append(parts[1])
    return list(dict.fromkeys(values))


def _owner(slot: dict, objects: dict[str, dict]) -> tuple[str | None, dict | None]:
    explicit = slot.get("authoring_object_id") or slot.get("owner_object_id")
    if isinstance(explicit, str) and explicit in objects:
        return explicit, objects[explicit]
    for candidate in _owner_candidates(str(slot.get("object_id") or "")):
        if candidate in objects:
            return candidate, objects[candidate]
    return None, None


def _render_path(directory: Path, page: int) -> Path | None:
    for name in (f"slide-{page}.png", f"page-{page}.png", f"slide_{page:02d}.png"):
        path = directory / name
        if path.is_file():
            return path.resolve()
    return None


def _bbox_norm(obj: dict) -> list[float] | None:
    value = obj.get("bbox")
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        box = [float(v) for v in value]
    except (TypeError, ValueError):
        return None
    if box[2] <= 0 or box[3] <= 0:
        return None
    return box


def _crop(path: Path, bbox: list[float], output: Path | None = None):
    from PIL import Image
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        x, y, w, h = bbox
        box = (
            max(0, int(round(x * rgb.width))),
            max(0, int(round(y * rgb.height))),
            min(rgb.width, int(round((x + w) * rgb.width))),
            min(rgb.height, int(round((y + h) * rgb.height))),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError("text bbox produces empty crop")
        crop = rgb.crop(box)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        crop.save(output)
    return crop, list(box)


def _foreground_geometry(image) -> dict:
    import numpy as np
    arr = np.asarray(image, dtype=np.float32)
    if arr.size == 0:
        raise ValueError("empty crop")
    h, w, _ = arr.shape
    border = np.concatenate([
        arr[0, :, :], arr[-1, :, :], arr[:, 0, :], arr[:, -1, :]
    ], axis=0)
    bg = np.median(border, axis=0)
    distance = np.sqrt(np.sum((arr - bg.reshape(1, 1, 3)) ** 2, axis=2))
    threshold = max(18.0, float(np.percentile(distance, 70)) * 0.55)
    mask = distance > threshold
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return {
            "foreground_bbox_px": [0, 0, 0, 0],
            "foreground_centroid_px": [w / 2.0, h / 2.0],
            "foreground_coverage": 0.0,
            "foreground_width_px": 0.0,
            "foreground_height_px": 0.0,
            "background_rgb": [round(float(v), 2) for v in bg],
            "threshold": round(threshold, 3),
        }
    left, top, right, bottom = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    return {
        "foreground_bbox_px": [left, top, right, bottom],
        "foreground_centroid_px": [round(float(xs.mean()), 3), round(float(ys.mean()), 3)],
        "foreground_coverage": round(float(mask.mean()), 6),
        "foreground_width_px": float(right - left),
        "foreground_height_px": float(bottom - top),
        "background_rgb": [round(float(v), 2) for v in bg],
        "threshold": round(threshold, 3),
    }


def _hierarchy_rank(slots: list[dict]) -> dict[str, int]:
    rows = []
    for slot in slots:
        target = float(slot.get("target_pt") or 0)
        if target > 0:
            rows.append((str(slot.get("object_id") or ""), target))
    sizes = sorted({size for _, size in rows}, reverse=True)
    size_rank = {size: index + 1 for index, size in enumerate(sizes)}
    return {slot_id: size_rank[size] for slot_id, size in rows}


def _classification(position_delta: float, scale_delta: float, coverage_delta: float, hierarchy_drift: bool,
                    position_tol: float, scale_tol: float, coverage_tol: float) -> str:
    if hierarchy_drift:
        return "hierarchy_drift"
    # Visible scale/weight changes can move the foreground centroid even when the
    # text anchor itself did not move. Classify those before pure position drift.
    if abs(scale_delta) > scale_tol or abs(coverage_delta) > coverage_tol:
        return "scale_or_weight_drift"
    if position_delta > position_tol:
        return "position_drift"
    return "aligned"


def analyze(text_fit: dict, authoring_plan: dict, reference_dir: Path, candidate_dir: Path,
            *, crop_dir: Path | None = None,
            position_tolerance_px: float = DEFAULT_POSITION_TOLERANCE_PX,
            scale_tolerance: float = DEFAULT_SCALE_TOLERANCE,
            coverage_tolerance: float = DEFAULT_COVERAGE_TOLERANCE) -> dict:
    issues: list[dict] = []
    objects = _object_index(authoring_plan)
    slots = [row for row in (text_fit.get("slots") or []) if isinstance(row, dict)]
    ranks = _hierarchy_rank(slots)
    records = []

    for slot in slots:
        owner_id, owner = _owner(slot, objects)
        if owner is None or owner_id is None:
            issues.append({"code": "text_render_owner_unknown", "slot": slot.get("object_id")})
            continue
        page = int(owner.get("page") or slot.get("slide") or 1)
        bbox = _bbox_norm(owner)
        if bbox is None:
            issues.append({"code": "text_render_bbox_invalid", "object_id": owner_id})
            continue
        ref_path = _render_path(reference_dir, page)
        cand_path = _render_path(candidate_dir, page)
        if ref_path is None or cand_path is None:
            issues.append({"code": "text_render_page_missing", "object_id": owner_id, "page": page})
            continue
        safe = _safe_id(owner_id)
        ref_out = crop_dir / "reference" / f"slide-{page}-{safe}.png" if crop_dir else None
        cand_out = crop_dir / "candidate" / f"slide-{page}-{safe}.png" if crop_dir else None
        ref_crop, crop_box = _crop(ref_path, bbox, ref_out)
        cand_crop, _ = _crop(cand_path, bbox, cand_out)
        ref_geom = _foreground_geometry(ref_crop)
        cand_geom = _foreground_geometry(cand_crop)

        rc, cc = ref_geom["foreground_centroid_px"], cand_geom["foreground_centroid_px"]
        position_delta = math.hypot(cc[0] - rc[0], cc[1] - rc[1])
        ref_h = max(1.0, float(ref_geom["foreground_height_px"]))
        cand_h = max(0.0, float(cand_geom["foreground_height_px"]))
        scale_delta = cand_h / ref_h - 1.0
        coverage_delta = float(cand_geom["foreground_coverage"]) - float(ref_geom["foreground_coverage"])

        rank = ranks.get(str(slot.get("object_id") or ""))
        hierarchy_drift = False
        target_pt = float(slot.get("target_pt") or 0)
        recommended_pt = float(slot.get("recommended_pt") or target_pt or 0)
        if rank is not None and target_pt > 0 and recommended_pt > 0:
            hierarchy_drift = recommended_pt / target_pt < 0.85 and rank <= 2

        classification = _classification(
            position_delta, scale_delta, coverage_delta, hierarchy_drift,
            position_tolerance_px, scale_tolerance, coverage_tolerance,
        )
        records.append({
            "object_id": owner_id,
            "text_slot_id": slot.get("object_id"),
            "page": page,
            "semantic_role": owner.get("semantic_role"),
            "target_pt": slot.get("target_pt"),
            "recommended_pt": slot.get("recommended_pt"),
            "hierarchy_rank": rank,
            "crop_bbox_px": crop_box,
            "reference": {
                "render_path": str(ref_path), "render_sha256": _sha256(ref_path),
                "crop_path": str(ref_out.resolve()) if ref_out else None, **ref_geom,
            },
            "candidate": {
                "render_path": str(cand_path), "render_sha256": _sha256(cand_path),
                "crop_path": str(cand_out.resolve()) if cand_out else None, **cand_geom,
            },
            "metrics": {
                "position_delta_px": round(position_delta, 3),
                "height_scale_delta": round(scale_delta, 6),
                "coverage_delta": round(coverage_delta, 6),
            },
            "classification": classification,
            "repair_required": classification != "aligned",
            "repair": {
                "classification": "text_render_feedback",
                "responsible_object": owner_id,
                "preferred_parameters": (
                    ["bbox", "baseline_offset", "alignment"] if classification == "position_drift"
                    else ["bbox", "margins", "line_spacing", "font_size"] if classification in {"scale_or_weight_drift", "hierarchy_drift"}
                    else []
                ),
                "font_shrink_last": True,
                "requires_fresh_render": classification != "aligned",
            },
        })

    return {
        "schema": SCHEMA,
        "valid": not issues,
        "diagnostic_only": True,
        "thresholds": {
            "position_tolerance_px": position_tolerance_px,
            "scale_tolerance": scale_tolerance,
            "coverage_tolerance": coverage_tolerance,
            "release_gate": False,
        },
        "summary": {
            "record_count": len(records),
            "repair_required_count": sum(bool(row["repair_required"]) for row in records),
            "hierarchy_drift_count": sum(row["classification"] == "hierarchy_drift" for row in records),
            "position_drift_count": sum(row["classification"] == "position_drift" for row in records),
            "scale_or_weight_drift_count": sum(row["classification"] == "scale_or_weight_drift" for row in records),
        },
        "records": records,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-fit-report", required=True, type=Path)
    parser.add_argument("--authoring-plan", required=True, type=Path)
    parser.add_argument("--reference-render-dir", required=True, type=Path)
    parser.add_argument("--candidate-render-dir", required=True, type=Path)
    parser.add_argument("--crop-dir", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--position-tolerance-px", type=float, default=DEFAULT_POSITION_TOLERANCE_PX)
    parser.add_argument("--scale-tolerance", type=float, default=DEFAULT_SCALE_TOLERANCE)
    parser.add_argument("--coverage-tolerance", type=float, default=DEFAULT_COVERAGE_TOLERANCE)
    args = parser.parse_args()
    report = analyze(
        _load(args.text_fit_report), _load(args.authoring_plan),
        args.reference_render_dir.resolve(), args.candidate_render_dir.resolve(),
        crop_dir=args.crop_dir.resolve() if args.crop_dir else None,
        position_tolerance_px=args.position_tolerance_px,
        scale_tolerance=args.scale_tolerance,
        coverage_tolerance=args.coverage_tolerance,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": report["valid"], **report["summary"], "report": str(args.report)}, ensure_ascii=False))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
