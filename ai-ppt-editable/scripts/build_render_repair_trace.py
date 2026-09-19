#!/usr/bin/env python3
"""Build an object-level render-review Repair Trace from local crop evidence.

The planner is deliberately threshold-free. Visual scores rank inspection and
repair work; they never decide whether a visually repairable page may proceed.
The planner maps weak regions to stable objects/semantic regions and emits
pattern-specific checks for typography density, asset identity and anchored
visual systems such as branded footer bands.
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
        for kind in ("texts", "shapes", "tables", "charts", "images", "icons", "groups", "panels", "connectors", "semantic_regions"):
            for spec in slide.get(kind) or []:
                if not isinstance(spec, dict):
                    continue
                oid = str(spec.get("object_id") or spec.get("text_id") or spec.get("name") or "").strip()
                if oid:
                    out[oid] = {"slide": slide_no, "kind": kind, "spec": spec}
    return out


def _is_footer_region(kind: str, oid: str, bbox: list | None, spec: dict | None) -> bool:
    role = str((spec or {}).get("semantic_role") or (spec or {}).get("role") or "").lower()
    token = f"{kind} {oid} {role}".lower()
    if any(word in token for word in ("footer", "bottom-band", "bottom_bar", "brand-band", "skyline")):
        return True
    if isinstance(bbox, list) and len(bbox) >= 4:
        try:
            return float(bbox[1]) >= 0.80 and float(bbox[2]) >= 0.45
        except (TypeError, ValueError):
            return False
    return False


def responsibility(kind: str, metrics: dict, *, oid: str = "", bbox: list | None = None, spec: dict | None = None) -> tuple[str, list[str]]:
    layout = float(metrics.get("layout_ssim", 0.0) or 0.0)
    pixel = float(metrics.get("pixel_fidelity", 0.0) or 0.0)
    if _is_footer_region(kind, oid, bbox, spec):
        return "anchored-visual-system", [
            "treat the footer wave/skyline/background as one semantic visual system when native fragmentation reduces fidelity",
            "compare the footer band's visible top edge, height and skyline baseline before moving foreground labels",
            "anchor 5G/brand marks to the footer semantic-region bbox, not to page center or an unrelated text baseline",
            "after footer geometry changes, re-check every child anchor and z-order in the same crop",
        ]
    if kind == "texts":
        return "typography-density", [
            "compare reference and candidate line count, line breaks, occupied glyph area and whitespace ratio",
            "repair the true text-slot bbox, inner margins and reserved icon/divider space before changing font size",
            "preserve reference line topology; a max-lines cap is insufficient when the reference uses an exact line count",
            "use the same runtime-resolved font face for measurement and PowerPoint authoring; verify CJK OOXML binding",
            "check paragraph spacing, line spacing, weight and emphasis runs after geometry is correct",
        ]
    if kind in {"images", "icons"}:
        return "asset-identity", [
            "compare artwork identity/contour first, then alpha-visible bbox and visual centroid",
            "do not substitute a generic native glyph or geometric approximation for a reference pictogram",
            "verify aspect ratio, scale, safe alpha padding, transparency, clipping and z-order",
            "regenerate only when the artwork itself is wrong; placement-only defects stay placement repairs",
        ]
    if kind in {"semantic-region", "semantic_regions"}:
        return "semantic-region", [
            "inspect the region as a composed visual system rather than optimizing one child object in isolation",
            "identify the responsible child layer(s), preserve already-correct neighbors, then re-render the whole region",
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


def _priority(row: dict, kind: str, bbox: list | None) -> float:
    score = float(row.get("score", 1.0) or 0.0)
    mismatch = max(0.0, 1.0 - min(score, 1.0))
    metrics = row.get("metrics") or {}
    pixel = float(metrics.get("pixel_fidelity", score) or 0.0)
    layout = float(metrics.get("layout_ssim", score) or 0.0)
    metric_gap = max(0.0, 1.0 - min(pixel, layout, 1.0))
    area = 0.0
    if isinstance(bbox, list) and len(bbox) >= 4:
        try:
            area = max(0.0, min(float(bbox[2]) * float(bbox[3]), 0.30))
        except (TypeError, ValueError):
            pass
    domain_bonus = 0.12 if kind in {"texts", "icons", "images", "semantic-region", "semantic_regions"} else 0.06
    issue_bonus = 0.10 if row.get("issues") else 0.0
    return round(mismatch * 0.55 + metric_gap * 0.20 + min(area / 0.30, 1.0) * 0.15 + domain_bonus + issue_bonus, 6)


def build_trace(layout: dict, regional: dict, *, max_actions: int = 12, min_actions: int = 3) -> dict:
    index = object_index(layout)
    actions = []
    for row in regional.get("regions") or []:
        if not isinstance(row, dict):
            continue
        slide, declared_kind, oid = parse_region_id(str(row.get("region_id") or ""))
        located = index.get(oid)
        kind = located["kind"] if located else declared_kind
        spec = located.get("spec") if located else None
        box = row.get("bbox")
        domain, checks = responsibility(kind, row.get("metrics") or {}, oid=oid, bbox=box, spec=spec)
        actions.append({
            "priority": _priority(row, kind, box),
            "slide": located["slide"] if located else slide,
            "region_id": row.get("region_id"),
            "object_id": oid,
            "object_kind": kind,
            "responsibility": domain,
            "region_score": row.get("score"),
            "metrics": row.get("metrics") or {},
            "bbox": box,
            "bbox_px": row.get("bbox_px"),
            "crop_evidence": row.get("crop_evidence"),
            "status": "pending-render-review",
            "recommended_checks": checks,
            "proposed_patch": {},
            "auto_patch_allowed": False,
        })
    actions.sort(key=lambda item: (-item["priority"], str(item.get("object_id"))))
    if actions:
        keep = min(max_actions, max(min_actions, min(len(actions), 5)))
        actions = actions[:keep]
    blockers = [
        issue for issue in regional.get("issues") or []
        if issue.get("severity") == "blocker"
        and issue.get("code") not in {"foreground_weighted_threshold_not_met", "regional_threshold_not_met", "visual_target_not_met"}
    ]
    return {
        "schema": "ai-ppt-plus/render-repair-trace/v2",
        "valid": not blockers,
        "selection_policy": "relative visual impact; inspect the 3-5 highest-impact regions without a fixed visual threshold",
        "regional_score": regional.get("foreground_weighted_score"),
        "hard_blockers": blockers,
        "pending_actions": actions,
        "accepted": [],
        "rejected": [],
        "policy": [
            "local crop evidence before scalar optimization",
            "no fixed SSIM/fidelity target for production repair selection",
            "map every repair to a stable object id or semantic region and responsible layer",
            "text-slot geometry and line topology before font shrink",
            "reference pictograms use faithful independent assets instead of generic native approximations",
            "anchored visual systems repair parent geometry before child anchors",
            "protect already-correct neighboring objects",
            "no blind numeric patch from scalar similarity alone",
            "re-render after each accepted repair batch",
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("layout", type=Path)
    p.add_argument("regional_report", type=Path)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--target", type=float, help="deprecated; accepted for CLI compatibility and ignored")
    p.add_argument("--max-actions", type=int, default=12)
    p.add_argument("--min-actions", type=int, default=3)
    a = p.parse_args()
    result = build_trace(load(a.layout), load(a.regional_report), max_actions=a.max_actions, min_actions=a.min_actions)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"schema": result["schema"], "valid": result["valid"], "pending": len(result["pending_actions"])}, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
