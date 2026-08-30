#!/usr/bin/env python3
"""Build a versioned, hash-backed handoff between the PPT workers.

The handoff is deliberately an evidence manifest, not a second source of
truth.  Route and worker artifacts remain authoritative; this file records
which revision and files were actually handed to the next stage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/handoff/v2"


def package_revision() -> str:
    manifest = Path(__file__).resolve().parents[1] / "assets" / "skill-package.json"
    try:
        value = json.loads(manifest.read_text(encoding="utf-8")).get("package_revision")
    except (OSError, json.JSONDecodeError):
        value = None
    return value if isinstance(value, str) and value else "unknown"


PACKAGE_REVISION = package_revision()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def parse_pages(value: str | None) -> list[int]:
    if not value:
        return []
    pages: set[int] = set()
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            lo, hi = (int(item.strip()) for item in token.split("-", 1))
            pages.update(range(lo, hi + 1))
        else:
            pages.add(int(token))
    return sorted(page for page in pages if page > 0)


def artifact(path: Path | None, *, required: bool = False) -> dict | None:
    if path is None:
        return None
    record = {"path": str(path.resolve()), "required": required, "exists": path.is_file()}
    if path.is_file():
        record.update({"sha256": sha256(path), "size_bytes": path.stat().st_size})
    else:
        record.update({"sha256": None, "size_bytes": None})
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--output", required=True)
    parser.add_argument("--project-id")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--revision", default="working")
    parser.add_argument("--package-revision", default=PACKAGE_REVISION)
    parser.add_argument("--current-stage", default="reconstruction")
    parser.add_argument("--gate-status", default="in-progress")
    parser.add_argument("--route-decision")
    parser.add_argument("--visual-plan")
    parser.add_argument("--visual-manifest")
    parser.add_argument("--visual-assertions")
    parser.add_argument("--workflow-state")
    parser.add_argument("--editable-layout")
    parser.add_argument("--pptx", required=True)
    parser.add_argument("--strip")
    parser.add_argument("--expected-pages", type=int, required=True)
    parser.add_argument("--completed-pages")
    parser.add_argument("--remaining-pages")
    parser.add_argument("--blocker", action="append", default=[])
    parser.add_argument("--latest-check", action="append", default=[])
    parser.add_argument("--backend", default="python-pptx")
    parser.add_argument("--next-action", default="continue downstream QA")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    route_path = Path(args.route_decision).resolve() if args.route_decision else None
    visual_plan = Path(args.visual_plan).resolve() if args.visual_plan else None
    visual_manifest = Path(args.visual_manifest).resolve() if args.visual_manifest else None
    visual_assertions = Path(args.visual_assertions).resolve() if args.visual_assertions else None
    workflow_state = Path(args.workflow_state).resolve() if args.workflow_state else None
    layout = Path(args.editable_layout).resolve() if args.editable_layout else None
    pptx = Path(args.pptx).resolve()
    strip = Path(args.strip).resolve() if args.strip else None
    route_data = read_json(route_path)
    route = route_data.get("route")
    project_id = args.project_id or route_data.get("project_id") or project.name
    completed = parse_pages(args.completed_pages)
    remaining = parse_pages(args.remaining_pages)
    if not args.completed_pages and not args.remaining_pages:
        remaining = list(range(1, args.expected_pages + 1))

    artifacts: dict[str, dict] = {}
    for name, path, required in (
        ("route_decision", route_path, True),
        ("visual_generation_plan", visual_plan, route == "visual-creation" and visual_plan is not None),
        ("visual_generation_manifest", visual_manifest, route == "visual-creation" and visual_manifest is not None),
        ("visual_assertions", visual_assertions, route == "visual-creation" and visual_assertions is not None),
        ("workflow_state", workflow_state, workflow_state is not None),
        ("editable_layout", layout, layout is not None),
        ("visual_deck_strip", strip, route == "visual-creation" and strip is not None),
        ("pptx", pptx, True),
    ):
        record = artifact(path, required=required)
        if record is not None:
            artifacts[name] = record

    approved = {}
    pptx_record = artifacts.get("pptx")
    if pptx_record:
        approved["pptx"] = pptx_record["path"]
        approved["pptx_sha256"] = pptx_record["sha256"]

    authority = {
        "visual": route_data.get("visual_authority"),
        "formal_content": route_data.get("formal_content_authority"),
        "route": route,
    }
    page_coverage = {
        "page_count": args.expected_pages,
        "completed": completed,
        "remaining": remaining,
        "covered": sorted(set(completed) | set(remaining)),
        "complete": sorted(set(completed) | set(remaining)) == list(range(1, args.expected_pages + 1)),
    }
    visual_status = "not-used" if route in {"reference-reconstruction", "native-authoring"} else ("passed" if visual_plan and visual_manifest else "pending")
    data = {
        "schema": SCHEMA,
        "project_id": project_id,
        "project_dir": str(project),
        "run_id": args.run_id,
        "revision": args.revision,
        "package_revision": args.package_revision,
        "current_stage": args.current_stage,
        "gate_status": args.gate_status,
        "route": route,
        "authorities": authority,
        "approved_artifacts": approved,
        "artifacts": artifacts,
        "cross_artifact": {
            "page_coverage": page_coverage,
            "expected_pages": args.expected_pages,
            "route_authority_consistent": bool(route and authority["visual"]),
            "pptx_present": bool(pptx_record and pptx_record.get("exists")),
            "workflow_state_present": bool(workflow_state and workflow_state.is_file()),
        },
        "worker_handoffs": {
            "visual": {"skill": "ai-ppt-visual-gen", "status": visual_status, "plan": str(visual_plan) if visual_plan else None, "manifest": str(visual_manifest) if visual_manifest else None, "assertions": str(visual_assertions) if visual_assertions else None},
            "editable": {"skill": "ai-ppt-editable", "status": "in-progress" if args.current_stage != "validated" else "passed", "layout": str(layout) if layout else None, "pptx": str(pptx)},
        },
        "completed_slides": completed,
        "active_batch": "B01",
        "remaining_slides": remaining,
        "open_blockers": list(args.blocker),
        "repair_round": 0,
        "latest_checks": list(args.latest_check),
        "backend": args.backend,
        "next_action": args.next_action,
        "capability_status": {"human_signoff": "pending", "human_visual_review": "pending"},
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    atomic_write_json(Path(args.output).resolve(), data)
    print(json.dumps({"schema": SCHEMA, "valid": True, "path": str(Path(args.output).resolve()), "project_id": project_id, "run_id": args.run_id}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
