#!/usr/bin/env python3
"""Combine font declaration, resolution and final-render evidence.

The three signals are intentionally separate. Font discovery alone cannot
prove that the final PPTX rendered visibly, and a sidecar font cannot prove
that a delivered PPTX carries an embedded font.

Usage: validate_font_delivery.py --font-report font-report.json
       --inspection inspection.json --render-report render-report.json
       --render-visual-gate render-visual-gate.json --report report.json
       [--font-asset-report font-asset-validation.json]
       [--target-review wps-target-review.json]
       [--profile wps|portable] [--require-embedded] [--require-target-review]
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


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
    parser.add_argument("--target-review")
    parser.add_argument("--profile", choices=["wps", "portable"], default="wps")
    parser.add_argument("--require-embedded", action="store_true")
    parser.add_argument("--require-target-review", action="store_true")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    font = load(args.font_report)
    asset = load(args.font_asset_report)
    inspection = load(args.inspection)
    render = load(args.render_report)
    visual = load(args.render_visual_gate)
    target = load(args.target_review)
    issues: list[dict] = []

    records = font.get("fonts", []) if font else []
    declared_values = sorted({str(record.get("requested")) for record in records if isinstance(record, dict) and record.get("requested")})
    declared_pass = bool(font and font.get("ok") is True and declared_values)
    if not declared_pass:
        issues.append({"severity": "blocker", "code": "declared_font_missing", "message": "font-report must contain at least one declared font family"})

    resolved_values = sorted({str(record.get("resolved")) for record in records if isinstance(record, dict) and record.get("resolved") and record.get("exact_or_family_match") is True})
    resolved_pass = bool(font and font.get("cjk_delivery_supported") is True and resolved_values)
    if asset and asset.get("valid") is not True:
        issues.append({"severity": "blocker", "code": "font_asset_invalid", "message": "font asset manifest validation failed", "asset_issues": asset.get("issues", [])})
    if not resolved_pass:
        issues.append({"severity": "blocker", "code": "resolved_font_missing", "message": "declared font did not resolve to a CJK-capable family", "resolved": resolved_values})

    rendered_pages = render.get("pages", []) if render else []
    visual_pages = visual.get("pages", []) if visual else []
    visible_page_stats = [page.get("stats", {}).get("nonuniform") is True for page in visual_pages if isinstance(page, dict)]
    render_visible_pass = bool(render and render.get("ok") is True and rendered_pages and visual and visual.get("valid") is True and visible_page_stats and all(visible_page_stats))
    if not render_visible_pass:
        issues.append({"severity": "blocker", "code": "render_not_visible", "message": "final PPTX render and non-blank visual gate must both pass"})

    embedded = bool((inspection or {}).get("embedded_fonts", {}).get("present"))
    if args.require_embedded and not embedded:
        issues.append({"severity": "blocker", "code": "embedded_font_missing", "message": "strict delivery requires verified OOXML embedded fonts"})

    device_results = (target or {}).get("devices", {}) if isinstance(target, dict) else {}
    desktop_wps = bool(device_results.get("desktop_wps") is True)
    iphone_wps = bool(device_results.get("iphone_wps") is True)
    target_review_pass = desktop_wps and iphone_wps
    if args.require_target_review and not target_review_pass:
        issues.append({"severity": "blocker", "code": "target_review_missing", "message": "desktop WPS and iPhone WPS review evidence is required"})

    output = {
        "schema": "ai-ppt-plus/font-delivery-validation/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": args.profile,
        "declared_font": {"pass": declared_pass, "families": declared_values},
        "resolved_font": {"pass": resolved_pass, "families": resolved_values, "cjk_delivery_supported": bool(font and font.get("cjk_delivery_supported"))},
        "render_visible": {"pass": render_visible_pass, "rendered_pages": len(rendered_pages), "visible_pages": sum(visible_page_stats)},
        "embedded_font": {"pass": embedded, "required": args.require_embedded, "evidence": (inspection or {}).get("embedded_fonts", {})},
        "target_review": {"pass": target_review_pass, "required": args.require_target_review, "devices": device_results},
        "issues": issues,
    }
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False))
    return 0 if output["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
