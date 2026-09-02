"""Regression coverage for the root P0 governance contracts."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, script, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="p0-governance-") as temp:
        project = Path(temp)
        outline = project / "outline.csv"
        outline.write_text(
            "slide_no,section,title,core_message,purpose,body_content,data_sources,visual_type,audience_takeaway,owner_notes,status,revision_reason\n"
            "1,总览,标题,结论,说明,正式内容,source.md#1,summary,记住结论,,approved,\n",
            encoding="utf-8",
        )
        source = project / "source.md"
        source.write_text("source", encoding="utf-8")
        contract = project / "outline-contract.json"
        built = run("scripts/build_outline_contract.py", str(outline), "--output", str(contract), "--project-id", "p0", "--revision", "R1", "--approval-status", "approved", "--approved-by", "owner", "--approved-at", "2026-08-31T00:00:00Z", "--source-reference", f"source={source}")
        assert built.returncode == 0, built.stdout + built.stderr
        checked = run("scripts/validate_outline_contract.py", str(contract), "--require-approved")
        assert checked.returncode == 0, checked.stdout + checked.stderr
        outline.write_text(outline.read_text(encoding="utf-8").replace("正式内容", "改过内容"), encoding="utf-8")
        stale = run("scripts/validate_outline_contract.py", str(contract), "--require-approved")
        assert stale.returncode == 2 and "outline_hash_mismatch" in stale.stdout, stale.stdout
        outline.write_text(outline.read_text(encoding="utf-8").replace("改过内容", "正式内容"), encoding="utf-8")

        manifest = project / "slide-object-manifest.json"
        write_json(manifest, {"slides": [{"slide_no": 1, "objects": [{"object_id": "title", "role": "formal-text", "content": "标题"}]}]})
        render = project / "slide-1.png"
        render.write_bytes(b"render")
        authority = project / "content-authority.json"
        write_json(authority, {
            "schema": "ai-ppt-plus/content-authority/v1", "project_id": "p0", "revision": "R1",
            "outline_contract": {"path": contract.name, "sha256": digest(contract)}, "sources": [{"source_id": "source", "path": source.name, "sha256": digest(source)}],
            "entries": [{"authority_id": "slide-1-title", "slide_no": 1, "object_id": "title", "role": "title", "content": "标题", "outline_ref": {"slide_no": 1, "field": "title"}, "source_refs": [{"source_id": "source"}], "pptx_object_ref": {"manifest_path": manifest.name, "object_id": "title"}, "render_ref": {"path": render.name, "bbox": [0, 0, 10, 10]} }],
        })
        authority_check = run("scripts/validate_content_authority.py", str(authority), "--require-pptx-refs", "--require-render-refs")
        assert authority_check.returncode == 0, authority_check.stdout + authority_check.stderr
        tampered_source = source.read_text(encoding="utf-8")
        source.write_text(tampered_source + " tampered", encoding="utf-8")
        source_blocked = run("scripts/validate_content_authority.py", str(authority))
        assert source_blocked.returncode == 2 and "source_hash_mismatch" in source_blocked.stdout, source_blocked.stdout
        source.write_text(tampered_source, encoding="utf-8")

        route = project / "route.json"
        write_json(route, {"schema": "ai-ppt-plus/route-decision/v1", "project_id": "p0", "route": "reference-reconstruction", "status": "decided", "visual_authority": "approved_reference_image", "formal_content_authority": "approved_outline", "requires_image_generation": False, "primary_engine": "ai-ppt-editable", "fallback_policy": "scoped-visual-only", "fallback_used": False, "fallback_events": [], "editable_object_policy": "native-semantic-objects", "outline_contract": {"path": contract.name, "sha256": digest(contract)}})
        workflow_artifact = project / "workflow-artifact"
        workflow_artifact.write_text("ok", encoding="utf-8")
        workflow = project / "workflow-state.json"
        write_json(workflow, {"project_id": "p0", "phase": "narrative-approved", "route": "reference-reconstruction", "approvals": {"outline": True}, "artifacts": {"outline": {"path": outline.name, "required": True, "sha256": digest(outline)}, "route": {"path": route.name, "required": True, "sha256": digest(route)}, "extra": {"path": workflow_artifact.name, "required": True, "sha256": digest(workflow_artifact)}}})
        gates = run("scripts/validate_orchestration_gates.py", str(project), "--outline-contract", str(contract), "--route-decision", str(route), "--workflow-state", str(workflow), "--strict")
        assert gates.returncode == 0, gates.stdout + gates.stderr
        broken = json.loads(workflow.read_text(encoding="utf-8")); broken["route"] = "native-authoring"; write_json(workflow, broken)
        blocked = run("scripts/validate_orchestration_gates.py", str(project), "--outline-contract", str(contract), "--route-decision", str(route), "--workflow-state", str(workflow), "--strict")
        assert blocked.returncode == 2 and "workflow_route_mismatch" in blocked.stdout, blocked.stdout

        quality = project / "quality-gates.json"
        write_json(quality, {"schema": "ai-ppt-plus/quality-gates/v1", "project_id": "p0", "revision": "R1", "technical_valid": True, "human_review_status": "pending", "release_eligible": False, "release_status": "blocked", "open_blockers": [], "dimensions": {name: {"status": "passed", "required": True} for name in ("content", "visual", "structure", "delivery")}})
        quality_check = run("scripts/validate_quality_gates.py", str(quality))
        assert quality_check.returncode == 0, quality_check.stdout + quality_check.stderr

    print("root P0 governance: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
