#!/usr/bin/env python3
"""Resolve external native-image generation responses and resume paused Astra cases.

Input response format per case:
{
  "assets": [
    {"object_id":"icon-1","file":"/path/icon.png","background_mode":"transparent","sha256":"..."}
  ]
}

The command validates every requested asset, binds it to the layout without
geometry drift, and emits a resume-ready layout. Missing or invalid assets keep
that case paused.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
EDITABLE = REPO / "ai-ppt-editable"
if str(EDITABLE) not in sys.path:
    sys.path.insert(0, str(EDITABLE))

from reconstruction.asset_orchestrator import AssetGenerationError, bind_generated_asset, validate_generated_asset


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _responses_by_object(payload: dict) -> dict[str, dict]:
    result = {}
    for item in payload.get("assets", []) or []:
        if isinstance(item, dict) and item.get("object_id"):
            result[str(item["object_id"])] = item
    return result


def resolve_case(*, layout: dict, requests: list[dict], responses: dict[str, dict], base_dir: Path | None = None) -> dict:
    deck = layout
    resolved = []
    missing = []
    invalid = []
    for request in requests:
        object_id = str(request.get("object_id") or "")
        response = responses.get(object_id)
        if response is None:
            missing.append(object_id)
            continue
        try:
            result = validate_generated_asset(request, response, base_dir=base_dir)
            bound = bind_generated_asset(deck, request, result)
            deck = bound["deck"]
            resolved.append(bound["report"])
        except AssetGenerationError as exc:
            invalid.append({"object_id": object_id, "error": str(exc)})
    ready = not missing and not invalid and len(resolved) == len(requests)
    return {
        "deck": deck,
        "report": {
            "schema": "ai-ppt-plus/generated-asset-resolution/v1",
            "ready": ready,
            "requested_count": len(requests),
            "resolved_count": len(resolved),
            "missing": missing,
            "invalid": invalid,
            "resolved": resolved,
            "status": "resume-ready" if ready else "external-asset",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--layout", type=Path, required=True)
    ap.add_argument("--repair-execution-report", type=Path, required=True)
    ap.add_argument("--responses", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    layout = read_json(args.layout.resolve())
    execution = read_json(args.repair_execution_report.resolve())
    requests = list(execution.get("regeneration_requests") or [])
    if not requests:
        raise SystemExit("repair execution report has no regeneration_requests")
    response_payload = read_json(args.responses.resolve())
    result = resolve_case(
        layout=layout,
        requests=requests,
        responses=_responses_by_object(response_payload),
        base_dir=args.responses.resolve().parent,
    )

    out = args.output_dir.resolve()
    write_json(out / "asset-resolved-layout.json", result["deck"])
    write_json(out / "asset-resolution-report.json", result["report"])
    write_json(out / "resume-ready.json", {
        "schema": "ai-ppt-plus/astra-resume-ready/v1",
        "ready": result["report"]["ready"],
        "status": result["report"]["status"],
        "layout": str(out / "asset-resolved-layout.json"),
        "resolved_count": result["report"]["resolved_count"],
        "requested_count": result["report"]["requested_count"],
    })
    print(json.dumps(result["report"], ensure_ascii=False, indent=2))
    if args.strict and not result["report"]["ready"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
