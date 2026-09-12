#!/usr/bin/env python3
"""Combine portable font declaration, resolution and final-render evidence.

The three signals are intentionally separate. Font discovery alone cannot
prove that the final PPTX rendered visibly, and a sidecar font cannot prove
that a delivered PPTX carries an embedded font.

Usage: validate_font_delivery.py --font-report font-report.json
       --inspection inspection.json --render-report render-report.json
       --render-visual-gate render-visual-gate.json --report report.json
       [--font-asset-report font-asset-validation.json]
       [--profile portable] [--require-embedded] [--require-weights]
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from atomic_output import atomic_write_json


def load(path: str | None) -> dict | None:
    if not path:
        return None
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-report", required=True)
    parser.add_argument("--font-asset-report")
    parser.add_argument("--inspection", required=True)
    parser.add_argument("--render-report", required=True)
    parser.add_argument("--render-visual-gate", required=True)
    parser.add_argument("--profile", choices=["portable"], default="portable")
    parser.add_argument("--require-embedded", action="store_true")
    parser.add_argument("--require-weights", action="store_true", help="require real 400/500/600/700 font faces in the discovered set")
    parser.add_argument("--finalizer-receipt")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    font = load(args.font_report)
    asset = load(args.font_asset_report)
    inspection = load(args.inspection)
    render = load(args.render_report)
    visual = load(args.render_visual_gate)
    finalizer = load(args.finalizer_receipt)
    issues: list[dict] = []

    # v2 separates filesystem discovery from the requested-family resolution
    # records.  Keep accepting the older ``fonts`` field for compatibility,
    # but prefer the explicit v2 resolution records for the declaration gate.
    records = []
    if font:
        candidate_records = font.get("requested")
        if isinstance(candidate_records, list) and candidate_records:
            records = candidate_records
        else:
            records = font.get("fonts", [])
    declared_values = sorted({str(record.get("requested")) for record in records if isinstance(record, dict) and record.get("requested")})
    declared_pass = bool(font and (font.get("ok") is True or font.get("valid") is True) and declared_values)
    if not declared_pass:
        issues.append({"severity": "blocker", "code": "declared_font_missing", "message": "font-report must contain at least one declared font family"})

    resolved_values = sorted({str(record.get("resolved")) for record in records if isinstance(record, dict) and record.get("resolved") and record.get("exact_or_family_match") is True})
    resolved_pass = bool(font and font.get("cjk_delivery_supported") is True and resolved_values)
    if asset and asset.get("valid") is not True:
        issues.append({"severity": "blocker", "code": "font_asset_invalid", "message": "font asset manifest validation failed", "asset_issues": asset.get("issues", [])})
    if not resolved_pass:
        issues.append({"severity": "blocker", "code": "resolved_font_missing", "message": "declared font did not resolve to a CJK-capable family", "resolved": resolved_values})
    required_weights = [400, 500, 600, 700]
    observed_weights = sorted({int(value) for value in (font or {}).get("weights_found", []) if isinstance(value, (int, float))})
    missing_weights = [weight for weight in required_weights if weight not in observed_weights]
    if args.require_weights and missing_weights:
        issues.append({"severity": "blocker", "code": "required_font_weights_missing", "required": required_weights, "observed": observed_weights, "missing": missing_weights})

    rendered_pages = (render.get("pages", []) if render else []) or (render.get("outputs", []) if render else [])
    visual_pages = visual.get("pages", []) if visual else []
    visible_page_stats = []
    for page in visual_pages:
        if not isinstance(page, dict):
            continue
        stats = page.get("stats")
        if not isinstance(stats, dict):
            final = page.get("final")
            stats = final.get("stats") if isinstance(final, dict) else None
        visible_page_stats.append(isinstance(stats, dict) and stats.get("nonuniform") is True)
    render_ok = bool(render and (render.get("ok") is True or render.get("valid") is True))
    page_count_match = bool(rendered_pages and len(visual_pages) == len(rendered_pages) and len(visible_page_stats) == len(rendered_pages))
    if not page_count_match:
        issues.append({"severity": "blocker", "code": "render_visual_page_count_mismatch", "rendered_pages": len(rendered_pages), "visual_pages": len(visual_pages)})
    render_visible_pass = bool(render_ok and page_count_match and visual and visual.get("valid") is True and visible_page_stats and all(visible_page_stats))
    if not render_visible_pass:
        issues.append({"severity": "blocker", "code": "render_not_visible", "message": "final PPTX render and non-blank visual gate must both pass"})

    resolved_set = set(resolved_values)
    actual_render_family = str(render.get("actual_render_family")) if render and render.get("actual_render_family") else ""
    actual_render_pass = bool(actual_render_family and actual_render_family in resolved_set and render.get("fallback") is False)
    if not actual_render_pass:
        issues.append({"severity": "blocker", "code": "actual_font_render_mismatch", "message": "final render must report the resolved family and fallback=false", "actual_render_family": actual_render_family, "resolved": sorted(resolved_set), "fallback": (render or {}).get("fallback")})

    embedded = bool((inspection or {}).get("embedded_fonts", {}).get("present"))
    if args.require_embedded and not embedded:
        issues.append({"severity": "blocker", "code": "embedded_font_missing", "message": "strict delivery requires verified OOXML embedded fonts"})

    output = {
        "schema": "ai-ppt-plus/font-delivery-validation/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": args.profile,
        "declared_font": {"pass": declared_pass, "families": declared_values},
        "resolved_font": {"pass": resolved_pass, "families": resolved_values, "cjk_delivery_supported": bool(font and font.get("cjk_delivery_supported")), "missing_weights": (font or {}).get("missing_weights", [])},
        "weight_coverage": {"pass": not missing_weights, "required": required_weights, "observed": observed_weights, "missing": missing_weights, "required_by_profile": args.require_weights},
        "actual_render": {"pass": actual_render_pass, "family": actual_render_family, "fallback": (render or {}).get("fallback")},
        "render_visible": {"pass": render_visible_pass, "rendered_pages": len(rendered_pages), "visible_pages": sum(visible_page_stats)},
        "embedded_font": {"pass": embedded, "required": args.require_embedded, "evidence": (inspection or {}).get("embedded_fonts", {})},
        "finalizer_font_evidence": {
            "upstream_native_font_rendering_verified": bool(((finalizer or {}).get("presentationLayout") or {}).get("font_policy", {}).get("native_font_rendering_verified") is True),
            "wrapper_compatibility_evidence": ((finalizer or {}).get("wrapperFontEvidence") or {}).get("allRequiredWeightsPresent") is True,
            "receipt_present": isinstance(finalizer, dict),
        },
        "issues": issues,
    }
    report = Path(args.report)
    atomic_write_json(report.resolve(), output)
    print(json.dumps(output, ensure_ascii=False))
    return 0 if output["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
