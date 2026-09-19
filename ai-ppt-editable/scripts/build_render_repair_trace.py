#!/usr/bin/env python3
"""Build an object-level render-review Repair Trace from local crop evidence.

This planner intentionally does not invent numeric geometry patches from scalar
scores. It maps weak rendered regions back to stable authoring objects, records
the evidence, and emits bounded next-check instructions for the responsible
layer. A human/agent can then repair the object and re-render.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def parse_region_id(region_id: str) -> tuple[int | None, str, str]:
    parts = region_id.split(":", 2)
    if len(parts) == 3 and parts[0].startswith("s"):
        try:
            slide = int(parts[0][1:])
        except ValueError:
            slide = None
        return slide, parts[1], parts[2]
    return None, "unknown", region_id


def object_index(deck: dict) -> dict[str, dict]:
    out = {}
    for slide_no, slide in enumerate(deck.get("slides") or [], 1):
        if not isinstance(slide, dict):
            continue
        for kind in ("texts", "shapes", "tables", "charts", "images", "icons", "groups", "panels", "connectors"):
            for spec in slide.get(kind) or []:
                if not isinstance(spec, dict):
                    continue
                oid = str(spec.get("object_id") or spec.get("text_id") or spec.get("name") or "").strip()
                if oid:
                    out[oid] = {"slide": slide_no, "kind": kind, "spec": spec}
    return out


def responsibility(kind: str, metrics: dict) -> tuple[str, list[str]]:
    layout = float(metrics.get("layout_ssim", 0.0) or 0.0)
    pixel = float(metrics.get("pixel_fidelity", 0.0) or 0.0)
    if kind == "texts":
        return "typography", [
            "compare same-coordinate crop for line count, baseline, bbox and internal margins",
            "repair text-slot geometry before shrinking font",
            "verify East Asian font family, weight, line spacing and emphasis runs",
        ]
    if kind in {"images", "icons"}:
        return "asset", [
            "compare alpha-visible bbox and visual centroid against the reference crop",
            "verify aspect ratio, scale, padding, transparency and clipping",
            "regenerate only when the asset artwork itself is wrong",
        ]
    if kind == "charts":
        return "chart", [
            "compare plot-area bbox, axis bounds, series geometry, labels and legend placement",
            "preserve known data and blank-value semantics",
            "prefer explicit label/plot geometry over viewer auto-layout when reference fidelity requires it",
        ]
    if kind == "tables":
        return "semantic-layout", [
            "reconfirm table-vs-repeated-component semantics",
            "compare row/column geometry, borders, cell margins and text baselines",
            "keep real table data native and independently editable",
        ]
    if kind in {"shapes", "panels", "groups", "connectors"}:
        checks = [
            "compare x/y/w/h, corner radius, stroke/fill and z-order against the reference crop",
            "repair the owning native object rather than compensating through neighboring text or icons",
        ]
        if layout >= 0.85 and pixel < 0.85:
            checks.append("geometry is relatively stable; inspect color/gradient/effect fidelity before moving the object")
        return "geometry", checks
    return "visual", ["inspect the crop and bind the finding to a stable authoring object before repair"]


def build_trace(layout: dict, regional: dict, *, target: float = 0.90, max_actions: int = 20) -> dict:
    index = object_index(layout)
    actions = []
    for row in regional.get("regions") or []:
        if not isinstance(row, dict):
            continue
        score = float(row.get("score", 0.0) or 0.0)
        if score >= target:
            continue
        slide, declared_kind, oid = parse_region_id(str(row.get("region_id") or ""))
        located = index.get(oid)
        kind = located["kind"] if located else declared_kind
        domain, checks = responsibility(kind, row.get("metrics") or {})
        actions.append({
            "priority": round(target - score, 6),
            "slide": located["slide"] if located else slide,
            "region_id": row.get("region_id"),
            "object_id": oid,
            "object_kind": kind,
            "responsibility": domain,
            "region_score": score,
            "metrics": row.get("metrics") or {},
            "bbox": row.get("bbox"),
            "bbox_px": row.get("bbox_px"),
            "crop_evidence": row.get("crop_evidence"),
            "status": "pending-render-review",
            "recommended_checks": checks,
            "proposed_patch": {},
            "auto_patch_allowed": False,
        })
    actions.sort(key=lambda item: (-item["priority"], str(item.get("object_id"))))
    actions = actions[:max_actions]
    blockers = [issue for issue in regional.get("issues") or [] if issue.get("severity") == "blocker" and issue.get("code") != "foreground_weighted_threshold_not_met"]
    return {
        "schema": "ai-ppt-plus/render-repair-trace/v1",
        "valid": not blockers,
        "target_reference_fidelity": target,
        "regional_score": regional.get("foreground_weighted_score"),
        "hard_blockers": blockers,
        "pending_actions": actions,
        "accepted": [],
        "rejected": [],
        "policy": [
            "local crop evidence before scalar optimization",
            "map every repair to a stable object id and responsible layer",
            "geometry/margins before font shrink",
            "protect already-passing neighboring objects",
            "no blind numeric patch from SSIM alone",
            "re-render after each accepted repair batch",
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("layout", type=Path)
    p.add_argument("regional_report", type=Path)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--target", type=float, default=0.90)
    p.add_argument("--max-actions", type=int, default=20)
    a = p.parse_args()
    result = build_trace(load(a.layout), load(a.regional_report), target=a.target, max_actions=a.max_actions)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"schema": result["schema"], "valid": result["valid"], "pending": len(result["pending_actions"])}, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
