#!/usr/bin/env python3
"""Build an object-level render-review Repair Trace from local crop evidence.

The planner is deliberately threshold-free. Visual scores rank inspection and
repair work; they never decide whether a visually repairable page may proceed.
The planner maps weak regions to stable objects/semantic regions and emits
pattern-specific checks for typography density, title-block geometry, composite
badge identity and anchored visual systems such as branded footer bands.
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


def _role(row: dict | None, spec: dict | None) -> str:
    values = []
    for source in (row or {}, spec or {}):
        for key in ("semantic_role", "role", "component_role", "visual_role"):
            if source.get(key):
                values.append(str(source[key]))
    return " ".join(values).lower()


def _is_footer_region(kind: str, oid: str, bbox: list | None, spec: dict | None, row: dict | None = None) -> bool:
    token = f"{kind} {oid} {_role(row, spec)}".lower()
    if any(word in token for word in ("footer", "bottom-band", "bottom_bar", "brand-band", "skyline")):
        return True
    if isinstance(bbox, list) and len(bbox) >= 4:
        try:
            return float(bbox[1]) >= 0.80 and float(bbox[2]) >= 0.45
        except (TypeError, ValueError):
            return False
    return False


def _is_title_region(kind: str, oid: str, bbox: list | None, spec: dict | None, row: dict | None = None) -> bool:
    if kind != "texts":
        return False
    token = f"{oid} {_role(row, spec)}".lower()
    explicit = ("title", "subtitle", "section-header", "column-header", "header-title", "title-block", "kicker")
    if any(word in token for word in explicit):
        return True
    if isinstance(bbox, list) and len(bbox) >= 4:
        try:
            return float(bbox[1]) <= 0.18 and float(bbox[2]) >= 0.25
        except (TypeError, ValueError):
            return False
    return False


def _is_composite_badge(kind: str, oid: str, spec: dict | None, row: dict | None = None) -> bool:
    if kind not in {"images", "icons", "groups", "shapes"}:
        return False
    token = f"{oid} {_role(row, spec)}".lower()
    return any(word in token for word in ("badge", "pictogram", "mini-icon", "icon-badge", "roundel", "medallion"))


def responsibility(kind: str, metrics: dict, *, oid: str = "", bbox: list | None = None, spec: dict | None = None, row: dict | None = None) -> tuple[str, list[str]]:
    layout = float(metrics.get("layout_ssim", 0.0) or 0.0)
    pixel = float(metrics.get("pixel_fidelity", 0.0) or 0.0)
    if _is_footer_region(kind, oid, bbox, spec, row):
        return "anchored-visual-system", [
            "treat the footer wave/skyline/background as one semantic visual system when native fragmentation reduces fidelity",
            "record the footer parent bbox plus normalized contour landmarks at several x positions; compare wave height/curvature, not only the rectangular bbox",
            "compare skyline baseline and visible top-edge profile before moving foreground labels",
            "anchor 5G/brand marks to the footer semantic-region bbox using normalized child anchors, not page coordinates or an unrelated text baseline",
            "repair order is parent bbox -> contour/asset crop -> skyline baseline -> child anchors -> z-order",
            "after footer geometry changes, re-check every child anchor and the whole footer crop",
        ]
    if _is_title_region(kind, oid, bbox, spec, row):
        return "title-block-geometry", [
            "treat title, subtitle, kicker/tag and divider as a title-block system instead of unrelated text boxes",
            "compare each slot x/y/w/h, first-baseline position, cap-height/visible glyph bbox and sibling gaps against the reference",
            "preserve reference line topology and run emphasis before changing font size",
            "do not compensate a wrong title slot by shrinking text or changing character spacing",
            "repair parent title-block geometry first, then child text slots, then typography and divider anchors",
        ]
    if _is_composite_badge(kind, oid, spec, row):
        return "composite-badge-identity", [
            "decompose the badge into background plate/roundel and foreground pictogram when both are visually meaningful",
            "compare plate diameter/radius, center and fill separately from the pictogram contour",
            "fit the pictogram by alpha-visible bbox and visual centroid, then anchor it to the plate center with explicit inset ratios",
            "keep nearby label text native; never bake readable label text into the badge asset",
            "re-render the complete badge plus label crop after repair",
        ]
    if kind == "texts":
        return "typography-density", [
            "compare reference and candidate line count, exact line breaks, occupied glyph area, baseline spacing and whitespace ratio",
            "repair the true text-slot bbox, inner margins and reserved icon/divider space before changing font size",
            "preserve reference line topology; a max-lines cap is insufficient when the reference uses an exact line count",
            "record target line-height/baseline delta and paragraph spacing as evidence, not only target_lines",
            "use the same runtime-resolved font face for measurement and PowerPoint authoring; verify CJK OOXML binding",
            "check weight, color and emphasis runs after geometry is correct",
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
            "record parent bbox, child normalized anchors and relationship constraints before repair",
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


def _priority(row: dict, kind: str, bbox: list | None, domain: str) -> float:
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
    domain_bonus = 0.14 if domain in {"title-block-geometry", "composite-badge-identity", "anchored-visual-system"} else 0.12 if kind in {"texts", "icons", "images", "semantic-region", "semantic_regions"} else 0.06
    issue_bonus = 0.10 if row.get("issues") else 0.0
    return round(mismatch * 0.55 + metric_gap * 0.20 + min(area / 0.30, 1.0) * 0.15 + domain_bonus + issue_bonus, 6)


def build_trace(layout: dict, regional: dict, *, max_actions: int = 12, min_actions: int = 3, target: float | None = None) -> dict:
    _ = target
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
        domain, checks = responsibility(kind, row.get("metrics") or {}, oid=oid, bbox=box, spec=spec, row=row)
        actions.append({
            "priority": _priority(row, kind, box, domain),
            "slide": located["slide"] if located else slide,
            "region_id": row.get("region_id"),
            "object_id": oid,
            "object_kind": kind,
            "semantic_role": _role(row, spec),
            "responsibility": domain,
            "region_score": row.get("score"),
            "metrics": row.get("metrics") or {},
            "bbox": box,
            "bbox_px": row.get("bbox_px"),
            "crop_evidence": row.get("crop_evidence"),
            "relationship_evidence": row.get("relationship_evidence") or {},
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
            "text-slot geometry, exact line topology and baseline spacing before font shrink",
            "title/subtitle/header geometry is repaired as a title-block system before typography compensation",
            "reference pictograms use faithful independent assets; composite badges separate plate geometry from pictogram identity",
            "anchored visual systems record parent contour landmarks and repair parent geometry before child anchors",
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
    result = build_trace(load(a.layout), load(a.regional_report), max_actions=a.max_actions, min_actions=a.min_actions, target=a.target)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"schema": result["schema"], "valid": result["valid"], "pending": len(result["pending_actions"])}, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
