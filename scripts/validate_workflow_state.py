#!/usr/bin/env python3
"""Validate the orchestrator's resumable workflow-state/v1 contract.

The state file is the small, durable control plane between O0-O5 and the two
worker skills. It records authority, phase, artifact paths and blockers. This
validator checks phase-specific readiness and, in strict mode, verifies every
required artifact hash without changing any project output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/workflow-state-validation/v1"
STATE_SCHEMA = "ai-ppt-plus/workflow-state/v1"
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
ROUTES = {"visual-creation", "reference-reconstruction", "native-authoring"}
PHASES = {
    "intake", "source-analyzed", "outline-draft", "outline-review",
    "narrative-approved", "design-system-ready", "visual-draft",
    "visual-approved", "reconstruction", "rendered", "validated",
    "revision-required", "human-closeout", "delivered",
}
PHASE_ORDER = {
    "intake": 0,
    "source-analyzed": 1,
    "outline-draft": 2,
    "outline-review": 3,
    "narrative-approved": 4,
    "design-system-ready": 5,
    "visual-draft": 6,
    "visual-approved": 7,
    "reconstruction": 8,
    "rendered": 9,
    "validated": 10,
    "human-closeout": 11,
    "delivered": 12,
}
EXPECTED_VISUAL_AUTHORITY = {
    "visual-creation": "generated_visual_intermediate",
    "reference-reconstruction": "approved_reference_image",
    "native-authoring": "approved_design_system",
}
BASE_REQUIREMENTS = {
    "source-analyzed": {"deck-brief", "source-inventory"},
    "outline-draft": {"deck-brief", "source-inventory", "outline"},
    "outline-review": {"deck-brief", "source-inventory", "outline"},
    "narrative-approved": {"deck-brief", "source-inventory", "outline"},
    "design-system-ready": {"deck-brief", "source-inventory", "outline", "design-system", "route-decision"},
    "visual-draft": {"deck-brief", "source-inventory", "outline", "design-system", "route-decision"},
    "visual-approved": {"deck-brief", "source-inventory", "outline", "design-system", "route-decision"},
    "reconstruction": {"deck-brief", "source-inventory", "outline", "design-system", "route-decision", "editable-layout"},
    "rendered": {"deck-brief", "source-inventory", "outline", "design-system", "route-decision", "editable-layout", "slide-manifest", "pptx", "render-report"},
    "validated": {"deck-brief", "source-inventory", "outline", "design-system", "route-decision", "editable-layout", "slide-manifest", "pptx", "render-report", "qa-report"},
    "human-closeout": {"deck-brief", "source-inventory", "outline", "design-system", "route-decision", "editable-layout", "slide-manifest", "pptx", "render-report", "qa-report", "human-signoff"},
    "delivered": {"deck-brief", "source-inventory", "outline", "design-system", "route-decision", "editable-layout", "slide-manifest", "pptx", "render-report", "qa-report", "human-signoff"},
}


def add_issue(issues: list[dict[str, Any]], code: str, **details: Any) -> None:
    issue = {"severity": "blocker", "code": code}
    issue.update({key: value for key, value in details.items() if value is not None})
    issues.append(issue)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(path: Path) -> str:
    records = []
    for child in sorted((item for item in path.rglob("*") if item.is_file()), key=lambda item: str(item.relative_to(path))):
        records.append({"path": str(child.relative_to(path)), "sha256": sha256(child), "size": child.stat().st_size})
    return hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def digest(path: Path) -> str:
    return sha256(path) if path.is_file() else tree_digest(path)


def resolve_path(raw: str, project_root: Path, issues: list[dict[str, Any]], artifact: str) -> Path | None:
    candidate = Path(raw)
    if not candidate.parts or any(part in {"", ".", ".."} for part in candidate.parts if not candidate.is_absolute()):
        add_issue(issues, "artifact_path_invalid", artifact=artifact, path=raw)
        return None
    return candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()


def artifact_record(raw: Any, artifact: str, issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        add_issue(issues, "artifact_record_invalid", artifact=artifact)
        return None
    path = raw.get("path")
    if not isinstance(path, str) or not path.strip():
        add_issue(issues, "artifact_path_missing", artifact=artifact)
        return None
    if "required" in raw and not isinstance(raw["required"], bool):
        add_issue(issues, "artifact_required_flag_invalid", artifact=artifact)
    declared = raw.get("sha256")
    if declared is not None and (not isinstance(declared, str) or not SHA256_RE.fullmatch(declared)):
        add_issue(issues, "artifact_hash_invalid", artifact=artifact)
    return raw


def required_artifacts(phase: str, route: str) -> set[str]:
    required = set(BASE_REQUIREMENTS.get(phase, set()))
    if phase in {"visual-draft", "visual-approved"} and route == "visual-creation":
        required.update({"visual-plan", "visual-manifest"})
    if phase == "visual-approved" and route == "visual-creation":
        required.add("deck-strip")
    if phase in {"design-system-ready", "visual-draft", "visual-approved"} and route == "reference-reconstruction":
        required.update({"reference-images", "reference-roster"})
    if phase in {"design-system-ready", "visual-draft", "visual-approved"} and route == "native-authoring":
        required.add("structured-content")
    return required


def validate_state(state_path: Path, project_root: Path, expected_pages: int | None, strict: bool, expected_package_revision: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, [{"severity": "blocker", "code": "workflow_state_unreadable", "message": f"{type(exc).__name__}: {exc}"}]
    if not isinstance(data, dict):
        return {}, [{"severity": "blocker", "code": "workflow_state_not_object"}]
    if data.get("schema") != STATE_SCHEMA:
        add_issue(issues, "workflow_state_schema_invalid", observed=data.get("schema"))
    for field in ("project_id", "run_id", "revision", "package_revision", "next_action", "updated_at"):
        if not isinstance(data.get(field), str) or not data.get(field, "").strip():
            add_issue(issues, "workflow_state_field_missing", field=field)
    if expected_package_revision is None:
        package_manifest = Path(__file__).resolve().parents[1] / "assets" / "skill-package.json"
        try:
            expected_package_revision = json.loads(package_manifest.read_text(encoding="utf-8")).get("package_revision")
        except (OSError, json.JSONDecodeError):
            expected_package_revision = None
    if expected_package_revision and data.get("package_revision") != expected_package_revision:
        add_issue(issues, "package_revision_mismatch", expected=expected_package_revision, observed=data.get("package_revision"))
    phase = data.get("phase")
    route = data.get("route")
    if phase not in PHASES:
        add_issue(issues, "workflow_state_phase_invalid", observed=phase, allowed=sorted(PHASES))
    if route not in ROUTES:
        add_issue(issues, "workflow_state_route_invalid", observed=route, allowed=sorted(ROUTES))
    page_count = data.get("page_count")
    if not isinstance(page_count, int) or isinstance(page_count, bool) or page_count < 1:
        add_issue(issues, "workflow_state_page_count_invalid", observed=page_count)
    elif expected_pages is not None and page_count != expected_pages:
        add_issue(issues, "workflow_state_page_count_mismatch", expected=expected_pages, observed=page_count)
    if data.get("canvas_ratio") not in {"16:9", "3:2"}:
        add_issue(issues, "workflow_state_canvas_ratio_invalid", observed=data.get("canvas_ratio"))

    formal = data.get("formal_text_authority")
    if not isinstance(formal, dict) or not isinstance(formal.get("kind"), str) or formal.get("kind") not in {"approved_outline", "user_transcription", "structured_content"}:
        add_issue(issues, "formal_text_authority_invalid")
    elif not isinstance(formal.get("approved"), bool):
        add_issue(issues, "formal_text_authority_approval_invalid")
    visual = data.get("visual_authority")
    expected_visual = EXPECTED_VISUAL_AUTHORITY.get(route)
    if not isinstance(visual, dict) or visual.get("kind") != expected_visual:
        add_issue(issues, "visual_authority_route_conflict", expected=expected_visual, observed=visual.get("kind") if isinstance(visual, dict) else None)
    elif not isinstance(visual.get("approved"), bool):
        add_issue(issues, "visual_authority_approval_invalid")

    artifacts_raw = data.get("artifacts")
    artifacts: dict[str, dict[str, Any]] = {}
    if not isinstance(artifacts_raw, dict):
        add_issue(issues, "workflow_state_artifacts_invalid")
    else:
        for name, raw in artifacts_raw.items():
            if not isinstance(name, str) or not name.strip():
                add_issue(issues, "artifact_name_invalid")
                continue
            record = artifact_record(raw, name, issues)
            if record is not None:
                artifacts[name] = record

    approvals = data.get("approvals")
    if approvals is not None and not isinstance(approvals, dict):
        add_issue(issues, "workflow_state_approvals_invalid")
        approvals = {}
    approvals = approvals if isinstance(approvals, dict) else {}
    if phase in {"narrative-approved", "design-system-ready", "visual-draft", "visual-approved", "reconstruction", "rendered", "validated", "human-closeout", "delivered"} and approvals.get("outline") is not True:
        add_issue(issues, "outline_approval_missing", phase=phase)
    if phase in {"design-system-ready", "visual-draft", "visual-approved", "reconstruction", "rendered", "validated", "human-closeout", "delivered"} and approvals.get("design_system") is not True:
        add_issue(issues, "design_system_approval_missing", phase=phase)
    if route == "visual-creation" and phase in {"visual-approved", "reconstruction", "rendered", "validated", "human-closeout", "delivered"} and approvals.get("visual") is not True:
        add_issue(issues, "visual_approval_missing", phase=phase)
    if phase in {"human-closeout", "delivered"} and approvals.get("human_closeout") is not True:
        add_issue(issues, "human_closeout_approval_missing", phase=phase)
    if phase in {"narrative-approved", "design-system-ready", "visual-draft", "visual-approved", "reconstruction", "rendered", "validated", "human-closeout", "delivered"} and isinstance(formal, dict) and formal.get("approved") is not True:
        add_issue(issues, "formal_text_not_approved", phase=phase)
    if phase == "visual-approved" and route == "visual-creation" and isinstance(visual, dict) and visual.get("approved") is not True:
        add_issue(issues, "visual_authority_not_approved", phase=phase)

    required = required_artifacts(phase, route) if phase in PHASES and route in ROUTES else set()
    artifact_evidence = {}
    for name in sorted(required):
        record = artifacts.get(name)
        if record is None:
            add_issue(issues, "required_artifact_not_declared", artifact=name, phase=phase)
            continue
        if record.get("required") is False:
            add_issue(issues, "required_artifact_declared_optional", artifact=name, phase=phase)
        path = resolve_path(record["path"], project_root, issues, name)
        evidence = {"path": str(path) if path else None, "required": True, "exists": bool(path and path.exists()), "sha256": None}
        if path is not None and path.exists():
            try:
                observed = digest(path)
            except OSError as exc:
                observed = None
                add_issue(issues, "artifact_digest_failed", artifact=name, message=f"{type(exc).__name__}: {exc}")
            evidence["sha256"] = observed
            declared = record.get("sha256")
            if strict and (not isinstance(declared, str) or not SHA256_RE.fullmatch(declared)):
                add_issue(issues, "required_artifact_hash_missing", artifact=name)
            elif declared and observed != declared:
                add_issue(issues, "artifact_hash_mismatch", artifact=name, expected=declared, observed=observed)
        else:
            add_issue(issues, "required_artifact_missing", artifact=name, path=str(path) if path else None)
        artifact_evidence[name] = evidence
    for name, record in artifacts.items():
        if name in required:
            continue
        path = resolve_path(record["path"], project_root, issues, name)
        evidence = {"path": str(path) if path else None, "required": bool(record.get("required")), "exists": bool(path and path.exists()), "sha256": None}
        if path and path.exists():
            try:
                observed = digest(path)
                evidence["sha256"] = observed
                if record.get("sha256") and observed != record.get("sha256"):
                    add_issue(issues, "artifact_hash_mismatch", artifact=name, expected=record.get("sha256"), observed=observed)
            except OSError as exc:
                add_issue(issues, "artifact_digest_failed", artifact=name, message=f"{type(exc).__name__}: {exc}")
        elif record.get("required") is True:
            add_issue(issues, "declared_required_artifact_missing", artifact=name, path=str(path) if path else None)
        artifact_evidence[name] = evidence

    blockers = data.get("open_blockers")
    if not isinstance(blockers, list):
        add_issue(issues, "open_blockers_invalid")
        blockers = []
    for index, blocker in enumerate(blockers):
        if not isinstance(blocker, dict):
            add_issue(issues, "blocker_record_invalid", index=index)
            continue
        for field in ("code", "severity", "owner_artifact", "status"):
            if not isinstance(blocker.get(field), str) or not blocker.get(field, "").strip():
                add_issue(issues, "blocker_field_missing", index=index, field=field)
        if blocker.get("status") == "resolved":
            add_issue(issues, "resolved_issue_in_open_blockers", index=index)
    if phase == "revision-required" and not blockers:
        add_issue(issues, "revision_state_without_blocker")
    if phase == "delivered" and blockers:
        add_issue(issues, "delivered_with_open_blockers")
    if phase == "delivered" and not isinstance(approvals.get("human_closeout"), bool):
        add_issue(issues, "delivered_human_approval_invalid")

    evidence = {
        "state": str(state_path),
        "state_sha256": sha256(state_path),
        "project_root": str(project_root),
        "phase": phase,
        "route": route,
        "required_artifacts": sorted(required),
        "artifacts": artifact_evidence,
        "strict": strict,
    }
    return evidence, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state")
    parser.add_argument("--project-root", help="base directory for relative artifact paths; defaults to the state file directory")
    parser.add_argument("--expected-pages", type=int)
    parser.add_argument("--expected-package-revision", help="override the local package manifest revision check")
    parser.add_argument("--strict", action="store_true", help="require current required artifacts and their SHA-256 declarations")
    parser.add_argument("--report")
    args = parser.parse_args()
    state_path = Path(args.state).resolve()
    project_root = Path(args.project_root).resolve() if args.project_root else state_path.parent
    try:
        evidence, issues = validate_state(state_path, project_root, args.expected_pages, args.strict, args.expected_package_revision)
    except Exception as exc:
        evidence = {}
        issues = [{"severity": "blocker", "code": "workflow_state_validation_failed", "message": f"{type(exc).__name__}: {exc}"}]
    result = {
        "schema": SCHEMA,
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "state": str(state_path),
        "project_root": str(project_root),
        "evidence": evidence,
        "issues": issues,
        "next_action": "continue pipeline" if not issues else "repair workflow state or its required artifacts",
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
