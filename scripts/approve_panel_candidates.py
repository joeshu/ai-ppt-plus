#!/usr/bin/env python3
"""Turn a human-reviewed panel candidate file into an approved asset manifest.

Approval is intentionally explicit. This command never infers that a
candidate is correct; ``--approve`` plus reviewer/revision metadata is the
required state transition. Optional ``--bbox`` and ``--exclude`` flags record
human corrections without changing the original candidate file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_bbox(raw: str):
    try:
        candidate_id, values = raw.split("=", 1)
        bbox = [int(round(float(value))) for value in values.split(",")]
    except (ValueError, TypeError):
        raise ValueError(f"invalid --bbox {raw!r}; use candidate-id=x,y,w,h")
    if not candidate_id or len(bbox) != 4 or bbox[2] <= 0 or bbox[3] <= 0 or bbox[0] < 0 or bbox[1] < 0:
        raise ValueError(f"invalid --bbox {raw!r}; use candidate-id=x,y,w,h with positive w,h")
    return candidate_id, bbox


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("candidates")
    ap.add_argument("--output", required=True)
    ap.add_argument("--approve", action="store_true", help="explicitly approve the reviewed candidates")
    ap.add_argument("--reviewer", help="human reviewer identity; required with --approve")
    ap.add_argument("--revision", help="revision identifier; required with --approve")
    ap.add_argument("--approved-at", help="ISO-8601 approval time; defaults to current UTC time")
    ap.add_argument("--bbox", action="append", default=[], help="correct a candidate: candidate-id=x,y,w,h")
    ap.add_argument("--exclude", action="append", default=[], help="exclude a candidate id after visual review")
    args = ap.parse_args()
    source = Path(args.candidates)
    if not source.is_file():
        ap.error(f"candidate manifest not found: {source}")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except Exception as exc:
        ap.error(f"invalid candidate JSON: {exc}")
    if data.get("status") != "needs-human-confirmation":
        ap.error("candidate manifest must have status=needs-human-confirmation")
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        ap.error("candidate manifest must contain non-empty candidates[]")
    if not args.approve:
        ap.error("refusing to approve without explicit --approve")
    if not args.reviewer or not args.revision:
        ap.error("--approve requires --reviewer and --revision")
    replacements = {}
    try:
        for raw in args.bbox:
            cid, bbox = parse_bbox(raw)
            if cid in replacements:
                ap.error(f"duplicate --bbox for {cid}")
            replacements[cid] = bbox
    except ValueError as exc:
        ap.error(str(exc))
    excluded = set(args.exclude)
    ids = {str(item.get("candidate_id")) for item in candidates if isinstance(item, dict)}
    unknown = (set(replacements) | excluded) - ids
    if unknown:
        ap.error(f"unknown candidate id(s): {', '.join(sorted(unknown))}")
    panels = []
    for item in candidates:
        if not isinstance(item, dict):
            ap.error("every candidate must be an object")
        cid = str(item.get("candidate_id", ""))
        if not cid or cid in excluded:
            continue
        bbox = replacements.get(cid, item.get("source_bbox"))
        if not isinstance(bbox, list) or len(bbox) != 4 or any(float(v) < 0 for v in bbox) or float(bbox[2]) <= 0 or float(bbox[3]) <= 0:
            ap.error(f"{cid}: source_bbox must be [x,y,w,h] with positive w,h")
        panels.append({
            "panel_id": cid,
            "file": f"{cid}.png",
            "source_bbox": [int(round(float(v))) for v in bbox],
            "treatment": "transparent-image",
            "formal_text_baked_in": False,
            "candidate_id": cid,
            "candidate_confidence": item.get("confidence"),
            "human_corrected": cid in replacements,
        })
    if not panels:
        ap.error("approval would produce no panels")
    approved_at = args.approved_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    source_path = data.get("source")
    source_file = Path(source_path) if source_path else None
    if source_file is not None and not source_file.is_absolute():
        source_file = source.parent / source_file
    if source_file is None or not source_file.is_file():
        ap.error("approved candidates must reference an existing source image so source_sha256 can be recorded")
    result = {
        "schema": "ai-ppt-plus/panel-assets/v1",
        "status": "approved",
        "source": source_path,
        "source_size": data.get("source_size"),
        "source_sha256": sha256(source_file),
        "whole_frame": False,
        "approval": {
            "reviewer": args.reviewer,
            "approved_at": approved_at,
            "revision": args.revision,
            "candidate_manifest": str(source.resolve()),
            "candidate_manifest_sha256": sha256(source),
            "excluded_candidate_ids": sorted(excluded),
            "corrected_candidate_ids": sorted(replacements),
        },
        "panels": panels,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": True, "status": result["status"], "panel_count": len(panels), "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
