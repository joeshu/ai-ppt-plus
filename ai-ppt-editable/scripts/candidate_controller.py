#!/usr/bin/env python3
"""Create and rank isolated region-level repair candidates.

The controller produces executable plans, not silent PPTX mutations. Each
candidate is an isolated branch of the reconstruction run with an explicit
scope, owner layer, expected checks, and stop conditions. A later authoring
worker may apply one plan in a fresh directory and feed its reports back to
``distillation_loop.py gate``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json


PLAN_SCHEMA = "ai-ppt-plus/distillation-candidate-plan/v1"
SELECTION_SCHEMA = "ai-ppt-plus/distillation-candidate-selection/v1"
SEVERITY_RANK = {"blocker": 0, "critical": 1, "major": 2, "minor": 3, "info": 4}

REPAIR_LIBRARY: dict[str, dict[str, Any]] = {
    "asset": {"operation": "rebind-source-asset", "mutations": ["recheck source crop", "preserve source_bbox and source_sha256", "rerun panel/icon extraction for affected regions"], "checks": ["validate_panel_assets", "validate_asset_hashes", "compare_visual"], "risk": "may change only the affected asset layer"},
    "font": {"operation": "recalibrate-and-embed-font", "mutations": ["use explicit task font directory", "rebuild typography calibration", "embed and validate CJK font"], "checks": ["validate_font_delivery", "validate_typography_calibration", "compare_visual"], "risk": "text metrics may move within the affected text regions"},
    "text": {"operation": "repair-native-text-layout", "mutations": ["keep formal copy immutable", "adjust only text box metrics and line breaks", "rerun text and overflow checks"], "checks": ["ocr_text_check", "validate_text_style_map", "validate_typography_calibration", "placement_qa"], "risk": "cannot invent or silently normalize unreadable formal text"},
    "layout": {"operation": "repair-local-layout", "mutations": ["replay source coordinates", "recompute affected bbox/ratio", "render only affected pages before full validation"], "checks": ["validate_regions", "validate_multipage_layout", "compare_visual_deck"], "risk": "local repair must not drift unrelated regions"},
    "object": {"operation": "repair-semantic-object-plan", "mutations": ["rebuild object manifest for affected region", "retain independent panels", "keep known formal content native"], "checks": ["validate_object_manifest", "semantic_object_audit", "compare_dual"], "risk": "must not replace the page with a whole-slide bitmap"},
    "provenance": {"operation": "refresh-provenance-bindings", "mutations": ["rehash source and derived assets", "refresh object/report bindings", "reject stale filenames with mismatched hashes"], "checks": ["validate_asset_hashes", "validate_report_bundle", "compare_dual"], "risk": "does not alter visible content by itself"},
    "report": {"operation": "rebuild-report-bundle", "mutations": ["regenerate child reports after the deck hash is final", "rebuild index and aggregate", "preserve human review pending"], "checks": ["validate_report_bundle", "validate_project", "validate_issue_log"], "risk": "report repair cannot hide an upstream failure"},
    "pipeline": {"operation": "rerun-scoped-pipeline", "mutations": ["backup current candidate", "rerun affected tasks with declared cache policy", "run full-deck validation after the repair batch"], "checks": ["run_pipeline", "validate_render", "compare_dual"], "risk": "stop after three repair rounds and escalate unresolved blockers"},
    "package": {"operation": "verify-package-boundary", "mutations": ["check package revision", "verify perfect-source sync", "run self-contained package validation"], "checks": ["validate_skill_package", "validate_perfect_sync", "run_tests"], "risk": "must not modify the pinned perfect baseline"},
}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def hash_key(*values: str) -> str:
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()[:12]


def owner_for(code: str, message: str = "") -> str:
    text = f"{code} {message}".lower()
    mapping = (
        ("package", ("package", "sync", "revision", "dependency")),
        ("font", ("font", "cjk", "glyph", "typeface")),
        ("text", ("text", "ocr", "copy", "typography", "wrap", "line_break")),
        ("layout", ("layout", "bbox", "overflow", "overlap", "ratio", "position", "coordinate")),
        ("object", ("object", "editable", "shape", "panel", "manifest")),
        ("provenance", ("hash", "source", "provenance", "stale")),
        ("asset", ("asset", "icon", "image", "background", "svg")),
        ("report", ("report", "registry", "evidence", "freshness")),
        ("pipeline", ("pipeline", "render", "compare", "cache", "timeout")),
    )
    for owner, words in mapping:
        if any(word in text for word in words):
            return owner
    return "pipeline"


def severity(item: dict[str, Any]) -> str:
    value = item.get("severity") or item.get("level")
    return value if value in SEVERITY_RANK else ("major" if item.get("status") in {"failed", "blocked", "open"} else "info")


def context(item: dict[str, Any]) -> dict[str, Any]:
    return {key: item[key] for key in ("slide", "slide_no", "page", "page_no", "object_id", "region_id", "region", "bbox", "source_bbox", "affected_pages", "affected_regions", "path") if key in item and item[key] not in (None, "", [])}


def collect_issues(data: Any, output: list[dict[str, Any]], *, inherited: dict[str, Any] | None = None) -> None:
    inherited = inherited or {}
    if isinstance(data, dict):
        local_context = {**inherited, **context(data)}
        if any(key in data for key in ("code", "message", "detail", "severity", "level")):
            code = str(data.get("code") or data.get("id") or "unspecified_issue")
            message = str(data.get("message") or data.get("detail") or code)
            output.append({"code": code, "message": message, "severity": severity(data), "owner": owner_for(code, message), "scope": local_context})
        for key, value in data.items():
            if key in {"issues", "errors", "warnings", "failed_steps", "technical_failed_steps", "feedback"}:
                collect_issues(value, output, inherited=local_context)
    elif isinstance(data, list):
        for value in data:
            collect_issues(value, output, inherited=inherited)


def dedupe_issues(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = json.dumps({"code": item["code"], "owner": item["owner"], "scope": item.get("scope", {})}, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return sorted(result, key=lambda item: (SEVERITY_RANK[item["severity"]], item["owner"], item["code"]))


def propose(reports: list[dict[str, Any]], *, base_candidate: str, max_proposals: int, max_repair_rounds: int) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for report in reports:
        collect_issues(report, issues)
    issues = dedupe_issues(issues)
    proposals: list[dict[str, Any]] = []
    for index, issue in enumerate(issues[:max_proposals], start=1):
        recipe = REPAIR_LIBRARY[issue["owner"]]
        proposal_id = f"p{index:02d}-{hash_key(base_candidate, issue['owner'], issue['code'], json.dumps(issue.get('scope', {}), sort_keys=True))}"
        proposals.append({
            "proposal_id": proposal_id,
            "candidate_id": f"{base_candidate}--{proposal_id}",
            "parent_candidate": base_candidate,
            "priority": index,
            "owner": issue["owner"],
            "trigger": {"code": issue["code"], "message": issue["message"], "severity": issue["severity"]},
            "scope": issue.get("scope", {}),
            "operation": recipe["operation"],
            "mutations": recipe["mutations"],
            "expected_checks": recipe["checks"],
            "risk": recipe["risk"],
            "isolation": {"directory_suffix": proposal_id, "backup_parent_first": True, "affected_only_first": True},
            "stop_conditions": {"max_repair_rounds": max_repair_rounds, "new_blocker": "rollback", "metric_regression": "rollback", "human_review": "required"},
            "auto_apply": False,
        })
    if not proposals:
        proposal_id = f"p01-{hash_key(base_candidate, 'baseline')}"
        proposals.append({"proposal_id": proposal_id, "candidate_id": f"{base_candidate}--baseline-check", "parent_candidate": base_candidate, "priority": 1, "owner": "pipeline", "trigger": {"code": "no-machine-feedback", "message": "No repair issue was emitted; rerun declared gates to establish a baseline.", "severity": "info"}, "scope": {"affected_pages": "all", "affected_regions": []}, "operation": "rerun-scoped-pipeline", "mutations": ["re-render declared pages", "rebuild dual comparison", "record fresh hashes"], "expected_checks": ["validate_render", "compare_dual", "validate_report_bundle"], "risk": "full-deck baseline check", "isolation": {"directory_suffix": "baseline-check", "backup_parent_first": True, "affected_only_first": False}, "stop_conditions": {"max_repair_rounds": max_repair_rounds, "new_blocker": "rollback", "metric_regression": "rollback", "human_review": "required"}, "auto_apply": False})
    return {"schema": PLAN_SCHEMA, "generated_at": datetime.now(timezone.utc).isoformat(), "base_candidate": base_candidate, "proposal_count": len(proposals), "source_issue_count": len(issues), "proposals": proposals, "execution_policy": "Plans are isolated and opt-in; no proposal may overwrite the previous baseline.", "human_visual_review_required": True}


def select(scores: list[dict[str, Any]], gates: list[dict[str, Any]]) -> dict[str, Any]:
    gate_by_id = {str(item.get("candidate_id")): item for item in gates if item.get("candidate_id")}
    eligible: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    rejected = []
    for score in scores:
        candidate_id = str(score.get("candidate_id") or "")
        gate = gate_by_id.get(candidate_id) or score.get("gate")
        if isinstance(gate, dict) and gate.get("decision") == "accept-for-human-review":
            eligible.append((float(score.get("weighted_score", 0.0)), score, gate))
        else:
            rejected.append({"candidate_id": candidate_id, "reason": (gate or {}).get("decision", "missing-accepted-gate")})
    eligible.sort(key=lambda item: (-item[0], str(item[1].get("candidate_id"))))
    selected = eligible[0] if eligible else None
    return {"schema": SELECTION_SCHEMA, "decision": "select-for-human-review" if selected else "keep-previous-candidate", "selected_candidate_id": selected[1].get("candidate_id") if selected else None, "selected_score": selected[0] if selected else None, "selected_gate": selected[2] if selected else None, "eligible_count": len(eligible), "rejected": rejected, "rollback_action": "promote_selected_candidate" if selected else "keep_previous_candidate", "human_visual_review_required": True, "human_review_status": "pending", "release_eligible": False}


def main() -> int:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    proposal = sub.add_parser("propose")
    proposal.add_argument("--report", action="append", required=True)
    proposal.add_argument("--base-candidate", default="candidate-0")
    proposal.add_argument("--max-proposals", type=int, default=8)
    proposal.add_argument("--max-repair-rounds", type=int, default=3)
    proposal.add_argument("--output", required=True)
    ranking = sub.add_parser("select")
    ranking.add_argument("--score", action="append", required=True)
    ranking.add_argument("--gate", action="append", default=[])
    ranking.add_argument("--output", required=True)
    args = root.parse_args()
    try:
        if args.command == "propose":
            result = propose([read_json(Path(value).resolve()) for value in args.report], base_candidate=args.base_candidate, max_proposals=max(1, args.max_proposals), max_repair_rounds=max(1, args.max_repair_rounds))
        else:
            result = select([read_json(Path(value).resolve()) for value in args.score], [read_json(Path(value).resolve()) for value in args.gate])
        atomic_write_json(Path(args.output).resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("decision") != "keep-previous-candidate" or args.command == "propose" else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": PLAN_SCHEMA, "valid": False, "status": "blocked", "code": "candidate_controller_failed", "message": str(exc)}, ensure_ascii=False))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
