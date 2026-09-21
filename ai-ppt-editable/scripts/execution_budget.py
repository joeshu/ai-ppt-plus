"""Collect and validate reconstruction work against an execution profile."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from execution_profiles import PROFILES

def _integer(value: Any, default: int = 0) -> int:
    try: return max(0, int(value))
    except (TypeError, ValueError): return default

def imagegen_usage(project: Path) -> tuple[int, dict[str, int]]:
    manifest = project / "imagegen-assets-manifest.json"
    if not manifest.is_file(): return 0, {}
    try: data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return 0, {}
    request_attempts, retries = {}, {}
    for index, asset in enumerate(data.get("assets") or [], 1):
        if not isinstance(asset, dict) or str(asset.get("provenance_mode") or "").lower() != "imagegen": continue
        asset_id = str(asset.get("asset_id") or asset.get("id") or f"asset-{index}")
        retry_count = _integer(asset.get("retry_count"))
        attempts = _integer(asset.get("generation_attempts") or asset.get("attempt_count"), 1)
        if retry_count == 0 and attempts > 1: retry_count = attempts - 1
        request_id = str(asset.get("generation_request_id") or asset.get("generation_batch_id") or asset_id)
        if asset.get("cache_hit") is not True:
            request_attempts[request_id] = max(request_attempts.get(request_id, 0), max(1, attempts))
        retries[asset_id] = retry_count
    return sum(request_attempts.values()), retries

def validate_usage(profile: str, *, candidate_build_count: int, full_render_count: int, imagegen_call_count: int, imagegen_retry_counts: dict[str, int], delivery: bool = True) -> dict:
    policy = PROFILES.get(profile)
    issues = []
    if policy is None:
        issues.append({"code":"execution_profile_unknown","profile":profile}); policy=PROFILES["fast"]
    if delivery and not policy["delivery_allowed"]:
        issues.append({"code":"execution_profile_not_delivery_capable","profile":profile})
    if candidate_build_count > policy["candidate_limit"]: issues.append({"code":"candidate_build_budget_exceeded","observed":candidate_build_count,"limit":policy["candidate_limit"]})
    if full_render_count > policy["full_render_limit"]: issues.append({"code":"full_render_budget_exceeded","observed":full_render_count,"limit":policy["full_render_limit"]})
    for asset_id,count in imagegen_retry_counts.items():
        if _integer(count) > policy["imagegen_retry_limit_per_asset"]: issues.append({"code":"imagegen_retry_budget_exceeded","asset_id":asset_id,"observed":_integer(count),"limit":policy["imagegen_retry_limit_per_asset"]})
    return {"schema":"ai-ppt-plus/execution-budget/v1","valid":not issues,"status":"passed" if not issues else "blocked","profile":profile,"policy":policy,"usage":{"candidate_build_count":candidate_build_count,"full_render_count":full_render_count,"imagegen_call_count":imagegen_call_count,"imagegen_retry_counts":imagegen_retry_counts},"issues":issues}
