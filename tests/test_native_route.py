#!/usr/bin/env python3
"""Regression coverage for the native-authoring route boundary."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: str, route: Path, report: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([
        sys.executable, script, str(route), "--require-files", "--expected-pages", "1",
        "--require-confirmation", "--require-formal-content", "--report", str(report),
    ], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="native-route-") as temp:
        project = Path(temp)
        native_manifest = project / "native-content-manifest.json"
        write_json(native_manifest, {
            "schema": "ai-ppt-plus/native-content-manifest/v1",
            "project_id": "native-route-fixture",
            "slides": [{"slide_no": 1, "content_source": "approved-outline.md", "native_objects": ["title"]}],
        })
        route = project / "route.json"
        write_json(route, {
            "schema": "ai-ppt-plus/route-decision/v2",
            "project_id": "native-route-fixture",
            "route": "native-authoring",
            "status": "decided",
            "visual_authority": "approved_design_system",
            "formal_content_authority": "approved_outline",
            "requires_image_generation": False,
            "native_content_manifest": native_manifest.name,
            "reference_roster": [],
            "reason": "",
            "confirmed_by": "test",
            "confirmed_at": "2026-08-29T00:00:00Z",
        })
        report = project / "route-validation.json"
        valid = run("scripts/validate_route.py", route, report)
        assert valid.returncode == 0, valid.stdout + valid.stderr
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["valid"] is True and data["route"] == "native-authoring", data
        child_report = project / "child-route-validation.json"
        child = run("ai-ppt-editable/scripts/validate_route.py", route, child_report)
        assert child.returncode == 0, child.stdout + child.stderr

        legacy = json.loads(route.read_text(encoding="utf-8"))
        legacy["schema"] = "ai-ppt-plus/route-decision/v1"
        write_json(route, legacy)
        blocked = run("scripts/validate_route.py", route, project / "legacy-report.json")
        assert blocked.returncode == 2 and "native_route_requires_v2" in blocked.stdout, blocked.stdout

    print("native route contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
