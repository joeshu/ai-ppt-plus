#!/usr/bin/env python3
"""Resolve external native-image generation responses and resume paused Astra cases.

Every generated asset must pass deterministic file validation and provider-neutral
visual QA. Failed visual QA can trigger at most three native generation attempts.
After the retry budget is exhausted the workflow stops at an explicit user-choice
boundary; it never switches to crop/matting automatically.
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
from reconstruction.asset_quality_qa import (
    AssetQualityThresholds,
    build_asset_quality_request,
    parse_asset_quality_response,
)
from reconstruction.asset_retry_policy import AssetRetryPolicy, next_retry_request


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


def build_quality_requests(*, requests: list[dict], responses: dict[str, dict], source_region_prefix: str) -> list[dict]:
    output = []
    for request in requests:
        object_id = str(request.get("object_id") or "")
        response = responses.get(object_id)
        if response is None:
            continue
        req = build_asset_quality_request(
            object_id=object_id,
            source_region_id=f"{source_region_prefix}#{object_id}",
            generated_asset_id=str(response.get("file") or ""),
            asset_kind=request.get("asset_kind") or request.get("kind"),
            generation_prompt=request.get("generation_prompt"),
            background_mode=request.get("background_mode"),
        )
        output.append(json.loads(req.to_json()))
    return output


def _attempt_count(request: dict, response: dict | None = None) -> int:
    values = [request.get("generation_attempt"), request.get("attempt")]
    if response:
        values.extend([response.get("generation_attempt"), response.get("attempt")])
    counts = []
    for value in values:
        try:
            if value is not None:
                counts.append(int(value))
        except (TypeError, ValueError):
            continue
    return max(counts or [1])


def resolve_case(*, layout: dict, requests: list[dict], responses: dict[str, dict],
                 quality_responses: dict[str, dict] | None = None,
                 thresholds: AssetQualityThresholds | None = None,
                 retry_policy: AssetRetryPolicy | None = None,
                 base_dir: Path | None = None) -> dict:
    deck = layout
    resolved = []
    missing = []
    invalid = []
    quality_rejected = []
    retry_requests = []
    user_choice_required = []
    quality_responses = quality_responses or {}
    thresholds = thresholds or AssetQualityThresholds()
    retry_policy = retry_policy or AssetRetryPolicy()

    for request in requests:
        object_id = str(request.get("object_id") or "")
        response = responses.get(object_id)
        if response is None:
            missing.append(object_id)
            continue
        try:
            result = validate_generated_asset(request, response, base_dir=base_dir)
        except AssetGenerationError as exc:
            invalid.append({"object_id": object_id, "error": str(exc)})
            continue

        quality_payload = quality_responses.get(object_id)
        if quality_payload is None:
            quality_rejected.append({"object_id": object_id, "error": "missing-asset-quality-qa"})
            continue
        try:
            quality = parse_asset_quality_response(
                quality_payload,
                expected_object_id=object_id,
                thresholds=thresholds,
            )
        except ValueError as exc:
            quality_rejected.append({"object_id": object_id, "error": str(exc)})
            continue

        if not quality["approved"]:
            quality_rejected.append({"object_id": object_id, "quality": quality})
            if quality.get("retry_native_generation"):
                current_attempt = _attempt_count(request, response)
                retry = next_retry_request(
                    request,
                    quality,
                    previous_attempts=current_attempt,
                    policy=retry_policy,
                )
                if retry["status"] == "retry-native-generation":
                    retry_requests.append(retry)
                else:
                    user_choice_required.append(retry)
            continue

        bound = bind_generated_asset(deck, request, result)
        deck = bound["deck"]
        report = dict(bound["report"])
        report["quality"] = quality
        report["generation_attempt"] = _attempt_count(request, response)
        resolved.append(report)

    ready = not missing and not invalid and not quality_rejected and len(resolved) == len(requests)
    status = "resume-ready" if ready else "user-choice-required" if user_choice_required else "external-asset"
    return {
        "deck": deck,
        "report": {
            "schema": "ai-ppt-plus/generated-asset-resolution/v3",
            "ready": ready,
            "requested_count": len(requests),
            "resolved_count": len(resolved),
            "missing": missing,
            "invalid": invalid,
            "quality_rejected": quality_rejected,
            "retry_native_generation": retry_requests,
            "user_choice_required": user_choice_required,
            "resolved": resolved,
            "status": status,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--layout", type=Path, required=True)
    ap.add_argument("--repair-execution-report", type=Path, required=True)
    ap.add_argument("--responses", type=Path, required=True)
    ap.add_argument("--quality-responses", type=Path)
    ap.add_argument("--source-region-prefix", default="reference-region")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--min-quality-score", type=float, default=0.88)
    ap.add_argument("--min-structure-score", type=float, default=0.90)
    ap.add_argument("--min-style-score", type=float, default=0.84)
    ap.add_argument("--max-native-attempts", type=int, default=3)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    layout = read_json(args.layout.resolve())
    execution = read_json(args.repair_execution_report.resolve())
    requests = list(execution.get("regeneration_requests") or [])
    if not requests:
        raise SystemExit("repair execution report has no regeneration_requests")
    response_payload = read_json(args.responses.resolve())
    responses = _responses_by_object(response_payload)
    quality_payload = read_json(args.quality_responses.resolve()) if args.quality_responses else {"assets": []}
    quality_responses = _responses_by_object(quality_payload)
    thresholds = AssetQualityThresholds(
        min_score=args.min_quality_score,
        min_structure_score=args.min_structure_score,
        min_style_score=args.min_style_score,
    )
    retry_policy = AssetRetryPolicy(max_native_attempts=args.max_native_attempts)

    out = args.output_dir.resolve()
    write_json(out / "asset-quality-qa-requests.json", {
        "schema": "ai-ppt-plus/asset-quality-qa-batch/v1",
        "assets": build_quality_requests(
            requests=requests,
            responses=responses,
            source_region_prefix=args.source_region_prefix,
        ),
    })

    result = resolve_case(
        layout=layout,
        requests=requests,
        responses=responses,
        quality_responses=quality_responses,
        thresholds=thresholds,
        retry_policy=retry_policy,
        base_dir=args.responses.resolve().parent,
    )

    write_json(out / "asset-resolved-layout.json", result["deck"])
    write_json(out / "asset-resolution-report.json", result["report"])
    write_json(out / "retry-native-generation.json", {
        "schema": "ai-ppt-plus/native-generation-retry-batch/v1",
        "assets": result["report"].get("retry_native_generation") or [],
    })
    write_json(out / "user-choice-required.json", {
        "schema": "ai-ppt-plus/asset-user-choice/v1",
        "required": bool(result["report"].get("user_choice_required")),
        "assets": result["report"].get("user_choice_required") or [],
    })
    write_json(out / "resume-ready.json", {
        "schema": "ai-ppt-plus/astra-resume-ready/v3",
        "ready": result["report"]["ready"],
        "status": result["report"]["status"],
        "layout": str(out / "asset-resolved-layout.json"),
        "resolved_count": result["report"]["resolved_count"],
        "requested_count": result["report"]["requested_count"],
        "retry_native_generation_count": len(result["report"].get("retry_native_generation") or []),
        "user_choice_required_count": len(result["report"].get("user_choice_required") or []),
    })
    print(json.dumps(result["report"], ensure_ascii=False, indent=2))
    if args.strict and not result["report"]["ready"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
