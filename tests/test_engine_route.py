#!/usr/bin/env python3
"""Regression coverage for the editable-first engine route contract."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assert_blocked(completed: subprocess.CompletedProcess[str], code: str) -> None:
    assert completed.returncode == 2, completed.stdout + completed.stderr
    assert code in completed.stdout, completed.stdout + completed.stderr


def editable_route() -> dict:
    return {
        "schema": "ai-ppt-plus/route-decision/v2",
        "project_id": "engine-route-fixture",
        "route": "reference-reconstruction",
        "status": "decided",
        "visual_authority": "approved_reference_image",
        "formal_content_authority": "approved_outline",
        "requires_image_generation": False,
        "primary_engine": "ai-ppt-editable",
        "fallback_policy": "scoped-visual-only",
        "fallback_used": False,
        "fallback_events": [],
        "editable_object_policy": "native-semantic-objects",
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="engine-route-") as temp:
        root = Path(temp)
        route_path = root / "route.json"
        route = editable_route()
        write(route_path, route)

        valid = run("scripts/validate_engine_route.py", str(route_path), "--strict")
        assert valid.returncode == 0, valid.stdout + valid.stderr

        legacy = copy.deepcopy(route)
        for key in ("primary_engine", "fallback_policy", "fallback_used", "fallback_events", "editable_object_policy"):
            legacy.pop(key)
        write(route_path, legacy)
        missing = run("scripts/validate_engine_route.py", str(route_path), "--strict")
        assert_blocked(missing, "primary_engine_missing")

        wrong_primary = editable_route()
        wrong_primary["primary_engine"] = "GordenImage2PPTX"
        write(route_path, wrong_primary)
        blocked_primary = run("scripts/validate_engine_route.py", str(route_path), "--strict")
        assert_blocked(blocked_primary, "primary_engine_forbidden")

        with_fallback = editable_route()
        with_fallback["fallback_used"] = True
        with_fallback["fallback_events"] = [{
            "engine": "GordenImage2PPTX",
            "scope": "region",
            "role": "complex-gradient",
            "object_type": "independent_image",
            "region": {"x": 0.10, "y": 0.10, "w": 0.25, "h": 0.20},
            "contains_formal_content": False,
            "whole_page": False,
            "reason": "native gradient primitive cannot reproduce the approved visual",
            "asset_record": {"manifest": "imagegen-assets-manifest.json", "asset_id": "gradient-01"},
            "user_decision": {"status": "approved", "by": "owner", "at": "2026-09-02T00:00:00Z"},
        }]
        write(route_path, with_fallback)
        scoped = run("scripts/validate_engine_route.py", str(route_path), "--strict")
        assert scoped.returncode == 0, scoped.stdout + scoped.stderr

        missing_declaration = copy.deepcopy(with_fallback)
        missing_declaration["fallback_events"][0].pop("contains_formal_content")
        write(route_path, missing_declaration)
        blocked_declaration = run("scripts/validate_engine_route.py", str(route_path), "--strict")
        assert_blocked(blocked_declaration, "fallback_formal_content_declaration_missing")

        forbidden_role = copy.deepcopy(with_fallback)
        forbidden_role["fallback_events"][0]["role"] = "table"
        write(route_path, forbidden_role)
        blocked_role = run("scripts/validate_engine_route.py", str(route_path), "--strict")
        assert_blocked(blocked_role, "fallback_role_forbidden")

        full_page = copy.deepcopy(with_fallback)
        full_page["fallback_events"][0]["whole_page"] = True
        write(route_path, full_page)
        blocked_full_page = run("scripts/validate_engine_route.py", str(route_path), "--strict")
        assert_blocked(blocked_full_page, "fallback_full_page_forbidden")

        visual_route = {
            "schema": "ai-ppt-plus/route-decision/v2",
            "project_id": "visual-route-fixture",
            "route": "visual-creation",
            "status": "decided",
            "visual_authority": "generated_visual_intermediate",
            "formal_content_authority": "approved_outline",
            "requires_image_generation": True,
            "primary_engine": "ai-ppt-visual-gen",
            "fallback_policy": "none",
            "fallback_used": True,
            "fallback_events": [with_fallback["fallback_events"][0]],
            "editable_object_policy": "image-slide",
        }
        write(route_path, visual_route)
        blocked_visual_fallback = run("scripts/validate_engine_route.py", str(route_path), "--strict")
        assert_blocked(blocked_visual_fallback, "fallback_not_allowed_for_route")

    print("editable-first engine route: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
