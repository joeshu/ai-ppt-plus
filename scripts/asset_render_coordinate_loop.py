#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA = "ai-ppt-plus/asset-render-coordinate/v1"
REPORT_SCHEMA = "ai-ppt-plus/asset-render-coordinate-report/v1"


def center(b):
    return [(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0]


def wh(b):
    return [b[2] - b[0], b[3] - b[1]]


def analyze(rec: dict) -> dict:
    oid = rec.get("object_id")
    asset = rec.get("asset") or {}
    slot = rec.get("slot") or {}
    render = rec.get("render") or {}
    issues = []
    try:
        aw, ah = map(float, asset["canvas_px"])
        ab = list(map(float, asset["alpha_bbox_px"]))
        ac = list(map(float, asset["alpha_centroid_px"]))
        rw, rh = map(float, render["canvas_px"])
        sb = list(map(float, slot["bbox_norm"]))
        ob = list(map(float, render["observed_visible_bbox_px"]))
    except Exception as exc:
        return {"object_id": oid, "valid": False, "issues": [{"code":"coordinate_record_invalid","detail":str(exc)}]}

    sx, sy, sw, sh = sb
    slot_px = [sx * rw, sy * rh, (sx + sw) * rw, (sy + sh) * rh]
    alpha_w, alpha_h = wh(ab)
    if min(aw, ah, alpha_w, alpha_h, sw, sh) <= 0:
        return {"object_id": oid, "valid": False, "issues": [{"code":"coordinate_extent_invalid"}]}

    # Fit full asset canvas into the PPT slot, preserving aspect ratio. The visible alpha
    # region is then projected through that exact transform.
    scale = min((sw * rw) / aw, (sh * rh) / ah)
    placed_w, placed_h = aw * scale, ah * scale
    origin = [slot_px[0] + ((sw * rw) - placed_w) / 2.0, slot_px[1] + ((sh * rh) - placed_h) / 2.0]
    expected = [origin[0] + ab[0] * scale, origin[1] + ab[1] * scale,
                origin[0] + ab[2] * scale, origin[1] + ab[3] * scale]
    expected_centroid = [origin[0] + ac[0] * scale, origin[1] + ac[1] * scale]
    observed_center = center(ob)
    expected_size = wh(expected)
    observed_size = wh(ob)
    centroid_delta = [observed_center[0] - expected_centroid[0], observed_center[1] - expected_centroid[1]]
    scale_delta = [observed_size[0] / expected_size[0] - 1.0, observed_size[1] / expected_size[1] - 1.0]
    bbox_delta = [ob[i] - expected[i] for i in range(4)]

    clipping = ob[0] < -0.5 or ob[1] < -0.5 or ob[2] > rw + 0.5 or ob[3] > rh + 0.5
    if clipping:
        issues.append({"code":"asset_render_clipping"})

    # These are diagnostics/repair deltas, not release-score gates.
    return {
        "object_id": oid,
        "valid": True,
        "asset_to_slot": {"scale": round(scale, 8), "origin_px": [round(x,3) for x in origin]},
        "expected_visible_bbox_px": [round(x,3) for x in expected],
        "expected_visual_centroid_px": [round(x,3) for x in expected_centroid],
        "observed_visible_bbox_px": [round(x,3) for x in ob],
        "centroid_delta_px": [round(x,3) for x in centroid_delta],
        "scale_delta_ratio": [round(x,6) for x in scale_delta],
        "visible_bbox_delta_px": [round(x,3) for x in bbox_delta],
        "repair": {
            "classification": "placement_only" if not clipping else "clipping_or_slot",
            "translate_px": [round(-x,3) for x in centroid_delta],
            "scale_ratio": [round(1.0/(1.0+x),6) if abs(1.0+x) > 1e-9 else None for x in scale_delta],
            "regenerate_asset": False
        },
        "issues": issues
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Map transparent asset alpha-space through PPT slot-space into final render-space.")
    p.add_argument("records", type=Path, help="JSON array or object with records[]")
    p.add_argument("--report", type=Path)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    try:
        data = json.loads(args.records.read_text(encoding="utf-8"))
        records = data.get("records", []) if isinstance(data, dict) else data
        if not isinstance(records, list):
            raise ValueError("records must be a JSON list")
        results = [analyze(x) for x in records if isinstance(x, dict)]
        invalid = [x for x in results if not x.get("valid")]
        report = {"schema": REPORT_SCHEMA, "valid": not invalid, "record_count": len(results), "records": results}
    except Exception as exc:
        report = {"schema": REPORT_SCHEMA, "valid": False, "record_count": 0, "records": [], "issues": [{"code":"coordinate_input_unreadable","detail":str(exc)}]}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json or not args.report:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
