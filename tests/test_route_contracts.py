#!/usr/bin/env python3
"""Regression tests for package identity and non-bypassable route decisions."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000000020001e221bc3300000000"
    "49454e44ae426082"
)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    package = run("scripts/validate_skill_package.py", "--skill-dir", str(ROOT))
    assert package.returncode == 0, package.stdout + package.stderr
    routing = run("scripts/validate_routing_contract.py")
    assert routing.returncode == 0, routing.stdout + routing.stderr

    with tempfile.TemporaryDirectory(prefix="route-contract-") as temp:
        root = Path(temp)
        reference = root / "reference.png"
        reference.write_bytes(PNG_1X1)
        digest = hashlib.sha256(PNG_1X1).hexdigest()
        route = root / "route.json"
        write_json(route, {
            "schema": "ai-ppt-plus/route-decision/v1",
            "project_id": "route-fixture",
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
            "reference_roster": [{"slide_no": 1, "path": "reference.png", "sha256": digest}],
            "visual_intermediate_manifest": None,
            "reason": "",
            "confirmed_by": "test",
            "confirmed_at": "2026-08-28T00:00:00Z",
        })
        report = root / "route-report.json"
        valid = run(
            "scripts/validate_route.py", str(route), "--require-files", "--expected-pages", "1",
            "--reference", str(reference), "--require-formal-content", "--report", str(report),
        )
        assert valid.returncode == 0, valid.stdout + valid.stderr
        result = json.loads(report.read_text(encoding="utf-8"))
        assert result["valid"] is True and result["ready_for_delivery"] is True, result
        assert result["evidence"]["external_reference_files"][0]["sha256"] == digest

        pending = json.loads(route.read_text(encoding="utf-8"))
        pending["status"] = "needs_user"
        pending["reason"] = "formal text needs confirmation"
        write_json(route, pending)
        blocked = run("scripts/validate_route.py", str(route), "--expected-pages", "1")
        assert blocked.returncode == 2, blocked.stdout + blocked.stderr
        assert "route_not_ready" in blocked.stdout

        release_project = root / "release-project"
        release_project.mkdir()
        release_deck = release_project / "deck.pptx"
        release_deck.write_bytes(b"placeholder deck")
        font_dir = release_project / "fonts"
        font_dir.mkdir()
        handoff = release_project / "handoff.json"
        signoff = release_project / "signoff.json"
        release_route = release_project / "route.json"
        write_json(release_route, {"status": "decided", "route": "visual-creation"})
        for path in (handoff, signoff):
            write_json(path, {})
        slide_manifest = release_project / "slide-manifest.json"
        write_json(slide_manifest, {"slides": [{"slide_no": 1}]})
        missing_declarations = run(
            "scripts/run_pipeline.py", str(release_project), "--deck", str(release_deck),
            "--expected-pages", "1", "--release", "--font-dir", str(font_dir),
            "--route-decision", str(release_route), "--handoff", str(handoff),
            "--human-signoff", str(signoff), "--quality-score", "100",
        )
        assert missing_declarations.returncode == 2, missing_declarations.stdout + missing_declarations.stderr
        assert "release_gate_requirements_missing" in missing_declarations.stdout

        gate_names = (
            "object_manifest", "semantic_object_audit", "manifest_registry", "text_model",
            "text_style_map", "icon_assets", "imagegen_assets", "panel_assets",
            "panel_approval", "gradient_visual", "source_image_validation", "reference_audit",
        )
        write_json(slide_manifest, {
            "gate_requirements": {name: name in {"object_manifest", "semantic_object_audit", "manifest_registry", "text_model"} for name in gate_names},
            "slides": [{"slide_no": 1}],
        })
        write_json(release_project / "slide-object-manifest.json", {
            "slides": [{"slide_no": 1, "objects": [{"object_id": "icon", "object_type": "extracted_icon"}]}],
        })
        underdeclared = run(
            "scripts/run_pipeline.py", str(release_project), "--deck", str(release_deck),
            "--expected-pages", "1", "--release", "--font-dir", str(font_dir),
            "--route-decision", str(release_route), "--handoff", str(handoff),
            "--human-signoff", str(signoff), "--quality-score", "100",
        )
        assert underdeclared.returncode == 2, underdeclared.stdout + underdeclared.stderr
        assert '"icon_assets"' in underdeclared.stdout

    print("package and route contracts: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
