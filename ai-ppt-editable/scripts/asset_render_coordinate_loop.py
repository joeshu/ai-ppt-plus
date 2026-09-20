#!/usr/bin/env python3
"""Bind transparent-asset geometry to a fresh PowerPoint render.

The coordinate loop is deliberately diagnostic.  It records the transform
from asset alpha-space to the authored slot and the observed final render,
then emits a small placement repair.  It never turns an artwork/identity
problem into an ImageGen retry and never introduces a page-level score gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "ai-ppt-plus/asset-render-coordinate/v1"
REPORT_SCHEMA = "ai-ppt-plus/asset-render-coordinate-report/v2"
DEFAULT_EPSILON_PX = 0.5


def _numbers(value: Any, count: int) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise ValueError(f"expected {count} numeric values")
    values = [float(item) for item in value]
    if not all(value == value and abs(value) != float("inf") for value in values):
        raise ValueError("non-finite coordinate")
    return values


def _bbox_width_height(box: list[float]) -> tuple[float, float]:
    return box[2] - box[0], box[3] - box[1]


def _center(box: list[float]) -> list[float]:
    return [(box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_path(value: Any, base_dir: Path | None) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path.resolve()


def _alpha_geometry(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - exercised in dependency probes
        raise RuntimeError("Pillow is required for automatic transparent-asset QA binding") from exc
    with Image.open(path) as source:
        native_mode = source.mode
        rgba = source.convert("RGBA")
        rgba.load()
    alpha = rgba.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("asset alpha is empty")
    left, top, right, bottom = bbox
    pixels = alpha.load()
    total = 0
    weighted_x = 0.0
    weighted_y = 0.0
    for y in range(rgba.height):
        for x in range(rgba.width):
            weight = int(pixels[x, y])
            total += weight
            weighted_x += x * weight
            weighted_y += y * weight
    if total <= 0:
        raise ValueError("asset alpha has no positive pixels")
    centroid = [weighted_x / total, weighted_y / total]
    return {
        "canvas_px": [rgba.width, rgba.height],
        "aspect_ratio": rgba.width / rgba.height,
        "alpha_bbox_px": [left, top, right, bottom],
        "alpha_centroid_px": centroid,
        "safe_padding_px": [left, top, rgba.width - right, rgba.height - bottom],
        "alpha_coverage": total / (255.0 * rgba.width * rgba.height),
        "native_mode": native_mode,
    }


def _load_qa_index(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("assets") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("asset QA report must contain an assets[] list")
    index: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        keys = [row.get(key) for key in ("asset_id", "object_id", "path", "asset_path", "copied_to")]
        for key in keys:
            if isinstance(key, str) and key:
                index[key] = row
                index[Path(key).name] = row
    return index


def _qa_row(asset: dict, qa_index: dict[str, dict]) -> dict | None:
    for key in ("asset_id", "object_id", "path", "asset_path", "file", "source_path"):
        value = asset.get(key)
        if isinstance(value, str) and value in qa_index:
            return qa_index[value]
        if isinstance(value, str) and Path(value).name in qa_index:
            return qa_index[Path(value).name]
    return None


def _bind_asset_qa(asset: dict, *, base_dir: Path | None, qa_index: dict[str, dict], auto: bool) -> tuple[dict, list[dict]]:
    bound = dict(asset)
    issues: list[dict] = []
    asset_path = _resolve_path(
        asset.get("path") or asset.get("asset_path") or asset.get("file") or asset.get("source_path"),
        base_dir,
    )
    qa = _qa_row(asset, qa_index)
    geometry: dict[str, Any] | None = None
    if auto and asset_path is not None and asset_path.is_file():
        try:
            geometry = _alpha_geometry(asset_path)
        except Exception as exc:
            issues.append({"code": "asset_qa_unreadable", "path": str(asset_path), "detail": str(exc)})
    elif auto and asset_path is not None:
        issues.append({"code": "asset_qa_asset_missing", "path": str(asset_path)})

    # A real file is authoritative for pixel geometry.  A precomputed QA row
    # remains useful when the task intentionally keeps the asset outside the
    # project directory, so it is used only for fields that are still absent.
    if geometry is not None:
        for key, value in geometry.items():
            if key not in bound or bound.get(key) in (None, ""):
                bound[key] = value
        bound["path"] = str(asset_path)
    if qa is not None:
        bound["qa_binding"] = {
            "status": "bound",
            "source": str(qa.get("path") or qa.get("asset_path") or qa.get("asset_id") or "asset-qa"),
        }
        for source_key, target_key in (
            ("size", "canvas_px"),
            ("alpha_bbox", "alpha_bbox_px"),
            ("alpha_centroid", "alpha_centroid_px"),
            ("transparent_padding", "safe_padding_px"),
        ):
            if target_key not in bound and source_key in qa:
                bound[target_key] = qa[source_key]
    elif geometry is not None:
        bound["qa_binding"] = {"status": "computed", "source": "rgba-alpha"}
    elif any(key not in bound for key in ("canvas_px", "alpha_bbox_px", "alpha_centroid_px")):
        issues.append({"code": "asset_qa_unbound", "object_id": asset.get("object_id") or asset.get("asset_id")})
    return bound, issues


def _render_path(render: dict, *, page: int | None, render_dir: Path | None, base_dir: Path | None) -> Path | None:
    # A pipeline render directory is the authoritative fresh candidate.  Do
    # not let a stale path serialized in an older coordinate record bypass the
    # current render/crop evidence.
    if render_dir is not None and page is not None:
        for name in (f"slide-{page}.png", f"page-{page}.png", f"slide_{page:02d}.png"):
            candidate = render_dir / name
            if candidate.is_file():
                return candidate.resolve()
    for key in ("path", "source", "render_path", "full_page_path"):
        path = _resolve_path(render.get(key), base_dir)
        if path is not None:
            return path
    return None


def _capture_crop(path: Path, box: list[float], output_dir: Path, object_id: str, page: int, margin: int) -> dict:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Pillow is required for final render crop capture") from exc
    with Image.open(path) as image:
        image.load()
        left, top, right, bottom = box
        crop_box = (
            max(0, int(round(left - margin))),
            max(0, int(round(top - margin))),
            min(image.width, int(round(right + margin))),
            min(image.height, int(round(bottom + margin))),
        )
        if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
            raise ValueError("observed visible bbox produces an empty crop")
        crop = image.crop(crop_box)
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", object_id).strip("._") or "object"
    output_dir.mkdir(parents=True, exist_ok=True)
    crop_path = output_dir / f"slide-{page}-{safe_id}.png"
    crop.save(crop_path)
    return {
        "full_page_path": str(path.resolve()),
        "full_page_sha256": _sha256(path),
        "crop_path": str(crop_path.resolve()),
        "crop_sha256": _sha256(crop_path),
        "crop_bbox_px": list(crop_box),
    }


def analyze(
    rec: dict,
    *,
    base_dir: Path | None = None,
    render_dir: Path | None = None,
    qa_index: dict[str, dict] | None = None,
    auto_bind_asset_qa: bool = False,
    capture_dir: Path | None = None,
    crop_margin_px: int = 12,
    require_render_evidence: bool = False,
    require_crop_evidence: bool = False,
    delta_epsilon_px: float = DEFAULT_EPSILON_PX,
) -> dict:
    oid = rec.get("object_id")
    issues: list[dict] = []
    if not isinstance(rec, dict):
        return {"object_id": oid, "valid": False, "issues": [{"code": "coordinate_record_invalid", "detail": "record must be an object"}]}
    if rec.get("schema") not in (None, SCHEMA):
        issues.append({"code": "coordinate_schema_mismatch", "observed": rec.get("schema")})
    asset, asset_issues = _bind_asset_qa(rec.get("asset") or {}, base_dir=base_dir, qa_index=qa_index or {}, auto=auto_bind_asset_qa)
    issues.extend(asset_issues)
    slot = rec.get("slot") or {}
    render = dict(rec.get("render") or {})
    try:
        aw, ah = _numbers(asset.get("canvas_px"), 2)
        ab = _numbers(asset.get("alpha_bbox_px"), 4)
        ac = _numbers(asset.get("alpha_centroid_px"), 2)
        sb = _numbers(slot.get("bbox_norm"), 4)
        rw, rh = _numbers(render.get("canvas_px"), 2)
        ob = _numbers(render.get("observed_visible_bbox_px"), 4)
    except Exception as exc:
        return {"object_id": oid, "valid": False, "issues": issues + [{"code": "coordinate_record_invalid", "detail": str(exc)}]}
    asset.setdefault("aspect_ratio", round(aw / ah, 8))
    asset.setdefault("visible_aspect_ratio", round(_bbox_width_height(ab)[0] / _bbox_width_height(ab)[1], 8))
    sx, sy, sw, sh = sb
    alpha_w, alpha_h = _bbox_width_height(ab)
    observed_w, observed_h = _bbox_width_height(ob)
    if min(aw, ah, alpha_w, alpha_h, sw, sh, rw, rh, observed_w, observed_h) <= 0:
        return {"object_id": oid, "valid": False, "issues": issues + [{"code": "coordinate_extent_invalid"}]}
    if ab[0] < 0 or ab[1] < 0 or ab[2] > aw or ab[3] > ah:
        issues.append({"code": "alpha_bbox_out_of_canvas", "alpha_bbox_px": ab, "canvas_px": [aw, ah]})
    if not (0 <= ac[0] <= aw and 0 <= ac[1] <= ah):
        issues.append({"code": "alpha_centroid_out_of_canvas", "alpha_centroid_px": ac})
    if sx < 0 or sy < 0 or sx + sw > 1.000001 or sy + sh > 1.000001:
        issues.append({"code": "slot_bbox_out_of_canvas", "bbox_norm": sb})
    slot_px = [sx * rw, sy * rh, (sx + sw) * rw, (sy + sh) * rh]
    scale = min((sw * rw) / aw, (sh * rh) / ah)
    placed_w, placed_h = aw * scale, ah * scale
    origin = [slot_px[0] + ((sw * rw) - placed_w) / 2.0, slot_px[1] + ((sh * rh) - placed_h) / 2.0]
    expected = [origin[0] + ab[0] * scale, origin[1] + ab[1] * scale, origin[0] + ab[2] * scale, origin[1] + ab[3] * scale]
    expected_centroid = [origin[0] + ac[0] * scale, origin[1] + ac[1] * scale]
    observed_center = _center(ob)
    observed_centroid = None
    if render.get("observed_visual_centroid_px") is not None:
        try:
            observed_centroid = _numbers(render.get("observed_visual_centroid_px"), 2)
        except Exception as exc:
            issues.append({"code": "observed_visual_centroid_invalid", "detail": str(exc)})
    expected_w, expected_h = _bbox_width_height(expected)
    scale_delta = [observed_w / expected_w - 1.0, observed_h / expected_h - 1.0]
    # A visible-bbox center is not an alpha-weighted visual centroid.  The two
    # coincide for symmetric icons but diverge badly for ribbons, skylines and
    # other low-frequency asymmetric art.  Keep bbox translation and centroid
    # evidence separate so a complex asset is not "repaired" from a false
    # centroid signal.
    bbox_center_delta = [observed_center[0] - _center(expected)[0], observed_center[1] - _center(expected)[1]]
    centroid_delta = (
        [observed_centroid[0] - expected_centroid[0], observed_centroid[1] - expected_centroid[1]]
        if observed_centroid is not None else None
    )
    bbox_delta = [ob[i] - expected[i] for i in range(4)]
    clipping = ob[0] < -0.5 or ob[1] < -0.5 or ob[2] > rw + 0.5 or ob[3] > rh + 0.5
    if clipping:
        issues.append({"code": "asset_render_clipping"})
    render_path = _render_path(render, page=rec.get("page"), render_dir=render_dir, base_dir=base_dir)
    if render_path is not None:
        render["path"] = str(render_path)
        if render_path.is_file():
            render["sha256"] = _sha256(render_path)
        elif require_render_evidence:
            issues.append({"code": "render_evidence_missing", "path": str(render_path), "page": rec.get("page"), "object_id": oid})
            render["sha256"] = None
    elif require_render_evidence:
        issues.append({"code": "render_evidence_missing", "page": rec.get("page"), "object_id": oid})
    crop_evidence = None
    if capture_dir is not None and render_path is not None and render_path.is_file():
        try:
            crop_evidence = _capture_crop(render_path, ob, capture_dir, str(oid or "object"), int(rec.get("page") or 1), crop_margin_px)
        except Exception as exc:
            issues.append({"code": "render_crop_capture_failed", "detail": str(exc)})
    elif require_crop_evidence:
        issues.append({"code": "render_crop_evidence_missing", "object_id": oid})
    centroid_terms = centroid_delta or []
    delta = max([abs(value) for value in centroid_terms + bbox_center_delta + bbox_delta] + [abs(value) * max(expected_w, expected_h) for value in scale_delta])
    repair_required = clipping or delta > delta_epsilon_px
    if repair_required and not clipping:
        classification = "placement_only"
    elif clipping:
        classification = "clipping_or_slot"
    else:
        classification = "aligned"
    result = {
        "object_id": oid,
        "page": rec.get("page"),
        "valid": not issues,
        "asset": asset,
        "slot": slot,
        "render": render,
        "asset_to_slot": {"scale": round(scale, 8), "origin_px": [round(value, 3) for value in origin]},
        "expected_visible_bbox_px": [round(value, 3) for value in expected],
        "expected_visual_centroid_px": [round(value, 3) for value in expected_centroid],
        "observed_visible_bbox_px": [round(value, 3) for value in ob],
        "observed_visual_centroid_px": [round(value, 3) for value in observed_centroid] if observed_centroid is not None else None,
        "centroid_delta_px": [round(value, 3) for value in centroid_delta] if centroid_delta is not None else None,
        "bbox_center_delta_px": [round(value, 3) for value in bbox_center_delta],
        "scale_delta_ratio": [round(value, 6) for value in scale_delta],
        "visible_bbox_delta_px": [round(value, 3) for value in bbox_delta],
        "repair_required": repair_required,
        "repair": {
            "classification": classification,
            "translate_px": [round(-value, 3) for value in (centroid_delta or bbox_center_delta)],
            "translation_basis": "observed_visual_centroid" if centroid_delta is not None else "visible_bbox_center",
            "scale_ratio": [round(1.0 / (1.0 + value), 6) if abs(1.0 + value) > 1e-9 else None for value in scale_delta],
            "regenerate_asset": False,
        },
        "render_evidence": crop_evidence,
        "issues": issues,
    }
    return result


def _load_records(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("records", []) if isinstance(data, dict) else data
    if not isinstance(records, list):
        raise ValueError("records must be a JSON list or an object with records[]")
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path, help="JSON array or object with records[]")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--base-dir", type=Path, help="base for relative asset/render evidence paths")
    parser.add_argument("--render-dir", type=Path, help="fresh render directory containing slide-N.png")
    parser.add_argument("--capture-crops", type=Path, help="write final-render object crops here")
    parser.add_argument("--crop-margin-px", type=int, default=12)
    parser.add_argument("--asset-qa-report", type=Path, help="transparent-asset QA report to bind by asset id/path")
    parser.add_argument("--auto-bind-asset-qa", action="store_true", help="read RGBA files and bind alpha geometry when fields are absent")
    parser.add_argument("--require-render-evidence", action="store_true")
    parser.add_argument("--require-crop-evidence", action="store_true")
    parser.add_argument("--require-records", action="store_true", help="fail when the coordinate inventory is empty")
    parser.add_argument("--delta-epsilon-px", type=float, default=DEFAULT_EPSILON_PX)
    args = parser.parse_args()
    try:
        if args.delta_epsilon_px < 0 or args.crop_margin_px < 0:
            raise ValueError("delta epsilon and crop margin must be non-negative")
        records = _load_records(args.records.resolve())
        base_dir = args.base_dir.resolve() if args.base_dir else args.records.resolve().parent
        render_dir = args.render_dir.resolve() if args.render_dir else None
        qa_path = args.asset_qa_report.resolve() if args.asset_qa_report else None
        qa_index = _load_qa_index(qa_path) if qa_path else {}
        if args.require_records and not records:
            report = {
                "schema": REPORT_SCHEMA,
                "valid": False,
                "status": "failed",
                "record_count": 0,
                "repair_loop_required": False,
                "records": [],
                "issues": [{"code": "coordinate_records_missing"}],
                "source": {"path": str(args.records.resolve()), "sha256": _sha256(args.records.resolve())},
            }
        else:
            results = [
                analyze(
                    item,
                    base_dir=base_dir,
                    render_dir=render_dir,
                    qa_index=qa_index,
                    auto_bind_asset_qa=args.auto_bind_asset_qa,
                    capture_dir=args.capture_crops.resolve() if args.capture_crops else None,
                    crop_margin_px=args.crop_margin_px,
                    require_render_evidence=args.require_render_evidence,
                    require_crop_evidence=args.require_crop_evidence,
                    delta_epsilon_px=args.delta_epsilon_px,
                )
                for item in records
            ]
            invalid = [item for item in results if not item.get("valid")]
            repair_items = [item for item in results if item.get("repair_required")]
            report = {
                "schema": REPORT_SCHEMA,
                "valid": not invalid,
                "status": "passed" if not invalid else "failed",
                "record_count": len(results),
                "repair_loop_required": bool(repair_items),
                "repair_required_count": len(repair_items),
                "placement_only_count": sum(item.get("repair", {}).get("classification") == "placement_only" for item in repair_items),
                "clipping_count": sum(item.get("repair", {}).get("classification") == "clipping_or_slot" for item in repair_items),
                "render_crop_evidence_count": sum(item.get("render_evidence") is not None for item in results),
                "asset_qa_bound_count": sum(bool((item.get("asset") or {}).get("qa_binding")) for item in results),
                "records": results,
                "issues": [issue for item in invalid for issue in item.get("issues", [])],
                "source": {"path": str(args.records.resolve()), "sha256": _sha256(args.records.resolve())},
            }
    except Exception as exc:
        report = {
            "schema": REPORT_SCHEMA,
            "valid": False,
            "status": "failed",
            "record_count": 0,
            "repair_loop_required": False,
            "records": [],
            "issues": [{"code": "coordinate_input_unreadable", "detail": f"{type(exc).__name__}: {exc}"}],
        }
    if args.report:
        args.report.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.report.resolve().write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json or not args.report:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
