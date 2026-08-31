#!/usr/bin/env python3
"""Create the hash-backed master contract for an outline table."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from atomic_output import atomic_write_json
from validate_outline import read_rows


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row_digest(row: dict) -> str:
    payload = {key: str(row.get(key) or "") for key in (
        "slide_no", "section", "title", "core_message", "purpose",
        "body_content", "data_sources", "visual_type", "audience_takeaway",
        "owner_notes", "status", "revision_reason",
    )}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outline")
    parser.add_argument("--output", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--outline-id", default="outline-main")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--approval-status", choices=["draft", "needs_user", "approved", "superseded", "blocked"], default="draft")
    parser.add_argument("--approved-by")
    parser.add_argument("--approved-at")
    parser.add_argument("--supersedes")
    parser.add_argument("--source-reference", action="append", default=[], metavar="ID=PATH")
    args = parser.parse_args()
    outline = Path(args.outline).resolve()
    try:
        rows = read_rows(outline)
    except Exception as exc:
        print(json.dumps({"valid": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 3
    if not rows:
        print(json.dumps({"valid": False, "error": "outline has no rows"}, ensure_ascii=False))
        return 2
    if args.approval_status == "approved" and (not args.approved_by or not args.approved_at):
        print(json.dumps({"valid": False, "error": "approved outline requires --approved-by and --approved-at"}, ensure_ascii=False))
        return 2
    refs = []
    for item in args.source_reference:
        if "=" not in item:
            print(json.dumps({"valid": False, "error": f"invalid source reference: {item}"}, ensure_ascii=False))
            return 2
        source_id, raw_path = item.split("=", 1)
        source_path = Path(raw_path).resolve()
        record = {"source_id": source_id, "path": raw_path, "sha256": sha256(source_path) if source_path.is_file() else None}
        refs.append(record)
    contract = {
        "schema": "ai-ppt-plus/outline-contract/v1",
        "project_id": args.project_id,
        "outline_id": args.outline_id,
        "outline_revision": args.revision,
        "outline_path": str(Path(args.outline).as_posix()),
        "outline_sha256": sha256(outline),
        "slide_count": len(rows),
        "approval": {"status": args.approval_status, "approved_by": args.approved_by, "approved_at": args.approved_at},
        "rows": [{"slide_no": int(row.get("slide_no")), "row_sha256": row_digest(row), "status": str(row.get("status") or ""), "title": str(row.get("title") or ""), "core_message": str(row.get("core_message") or ""), "body_content": str(row.get("body_content") or "")} for row in rows],
        "source_references": refs,
        "supersedes": args.supersedes,
        "change_log": [{"revision": args.revision, "reason": "initial contract"}],
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    output = Path(args.output).resolve()
    atomic_write_json(output, contract)
    print(json.dumps({"schema": contract["schema"], "valid": True, "path": str(output), "outline_sha256": contract["outline_sha256"], "slide_count": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
