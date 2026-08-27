#!/usr/bin/env python3
"""Validate ai-ppt-plus R13 gradient visual routing manifest."""
import argparse, json
from pathlib import Path

VALID_ROUTES = {"B2", "B3", "B4", "native"}
VALID_ROLES = {"background_blend", "frame", "element", "native_gradient"}
EXPECTED = {"background_blend": "B2", "frame": "B3", "element": "B4", "native_gradient": "native"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--report")
    ap.add_argument("--require-verified", action="store_true")
    a = ap.parse_args()
    path = Path(a.manifest)
    issues = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        data = {}; issues.append({"code":"invalid_manifest","message":str(exc)})
    if data.get("schema") != "ai-ppt-plus/gradient-visual/v1":
        issues.append({"code":"schema_mismatch"})
    regions = []
    for slide in data.get("slides", []):
        for region in slide.get("regions", []):
            regions.append(region)
            role = region.get("role"); route = region.get("route")
            if role not in VALID_ROLES: issues.append({"code":"invalid_role","id":region.get("id"),"value":role})
            if route not in VALID_ROUTES: issues.append({"code":"invalid_route","id":region.get("id"),"value":route})
            if role in EXPECTED and route != EXPECTED[role]: issues.append({"code":"role_route_mismatch","id":region.get("id"),"role":role,"route":route})
            # R13 rule: B2 background blends may be opaque when they own the background.
            if role != "background_blend" and region.get("requires_alpha") and not region.get("alpha_verified"):
                issues.append({"code":"alpha_not_verified","id":region.get("id")})
            if a.require_verified:
                if not region.get("embedded"): issues.append({"code":"not_embedded","id":region.get("id")})
                if not region.get("render_visible"): issues.append({"code":"not_render_visible","id":region.get("id")})
    if not regions: issues.append({"code":"no_gradient_regions"})
    report = {"schema":"ai-ppt-plus/gradient-visual-validation/v1","valid":not issues,"status":"passed" if not issues else "blocked","regions":len(regions),"issues":issues}
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
