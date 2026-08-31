#!/usr/bin/env python3
"""Run the root skill's cross-artifact P0 phase and route gates."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from atomic_output import atomic_write_json

ROUTES = {"visual-creation", "reference-reconstruction", "native-authoring"}
PHASES = ("intake", "source-analyzed", "outline-draft", "outline-review", "narrative-approved", "design-system-ready", "visual-draft", "visual-approved", "reconstruction", "rendered", "validated", "revision-required", "human-closeout", "delivered")
PHASE_ORDER = {name: index for index, name in enumerate(PHASES)}
EXPECTED_AUTHORITY = {"visual-creation": "generated_visual_intermediate", "reference-reconstruction": "approved_reference_image", "native-authoring": "approved_design_system"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read(path: Path, issues: list[dict], label: str):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        issues.append({"severity": "blocker", "code": f"{label}_unreadable", "message": f"{type(exc).__name__}: {exc}", "path": str(path)})
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--outline-contract", required=True)
    parser.add_argument("--route-decision", required=True)
    parser.add_argument("--workflow-state")
    parser.add_argument("--stage")
    parser.add_argument("--report")
    parser.add_argument("--strict", action="store_true", help="require route binding and artifact freshness")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    issues: list[dict] = []
    contract_path = Path(args.outline_contract).resolve()
    route_path = Path(args.route_decision).resolve()
    contract = read(contract_path, issues, "outline_contract")
    route = read(route_path, issues, "route_decision")
    state_path = Path(args.workflow_state).resolve() if args.workflow_state else None
    state = read(state_path, issues, "workflow_state") if state_path else {}
    if contract.get("schema") != "ai-ppt-plus/outline-contract/v1": issues.append({"severity":"blocker","code":"outline_contract_schema_invalid"})
    if route.get("route") not in ROUTES: issues.append({"severity":"blocker","code":"route_invalid","observed":route.get("route")})
    if route.get("status") != "decided": issues.append({"severity":"blocker","code":"route_not_decided","status":route.get("status")})
    route_name = route.get("route")
    expected = EXPECTED_AUTHORITY.get(route_name)
    if expected and route.get("visual_authority") != expected: issues.append({"severity":"blocker","code":"visual_authority_mismatch","expected":expected,"observed":route.get("visual_authority")})
    if route_name == "visual-creation" and route.get("requires_image_generation") is not True: issues.append({"severity":"blocker","code":"image_generation_requirement_missing"})
    if route_name in {"reference-reconstruction", "native-authoring"} and route.get("requires_image_generation") is not False: issues.append({"severity":"blocker","code":"unexpected_image_generation_requirement"})
    formal = route.get("formal_content_authority")
    if formal not in {"approved_outline", "user_transcription"}: issues.append({"severity":"blocker","code":"formal_content_not_ready","observed":formal})
    binding = route.get("outline_contract")
    if args.strict:
        if not isinstance(binding, dict): issues.append({"severity":"blocker","code":"route_outline_contract_binding_missing"})
        else:
            if binding.get("path") and Path(binding["path"]).name != contract_path.name and Path(binding["path"]).as_posix() != contract_path.as_posix():
                issues.append({"severity":"blocker","code":"route_outline_contract_path_mismatch"})
            if binding.get("sha256") != (sha256(contract_path) if contract_path.is_file() else None): issues.append({"severity":"blocker","code":"route_outline_contract_hash_mismatch"})
            if route.get("project_id") and contract.get("project_id") and route.get("project_id") != contract.get("project_id"):
                issues.append({"severity":"blocker","code":"route_project_mismatch"})
    stage = args.stage or state.get("phase") or "intake"
    if stage not in PHASE_ORDER: issues.append({"severity":"blocker","code":"stage_invalid","observed":stage})
    if state:
        if state.get("route") != route_name: issues.append({"severity":"blocker","code":"workflow_route_mismatch","workflow":state.get("route"),"route":route_name})
        if state.get("project_id") and contract.get("project_id") and state.get("project_id") != contract.get("project_id"): issues.append({"severity":"blocker","code":"workflow_project_mismatch"})
        if PHASE_ORDER.get(stage, 0) >= PHASE_ORDER["narrative-approved"] and not state.get("approvals", {}).get("outline", False): issues.append({"severity":"blocker","code":"outline_approval_missing"})
        if args.strict:
            for name, record in (state.get("artifacts") or {}).items():
                if not isinstance(record, dict) or not record.get("required"): continue
                raw = record.get("path")
                artifact_path = Path(raw) if isinstance(raw, str) and Path(raw).is_absolute() else project / str(raw or "")
                if not artifact_path.is_file(): issues.append({"severity":"blocker","code":"required_artifact_missing","artifact":name})
                elif record.get("sha256") and record.get("sha256") != sha256(artifact_path): issues.append({"severity":"blocker","code":"required_artifact_hash_mismatch","artifact":name})
    result = {"schema":"ai-ppt-plus/orchestration-gates/v1","valid":not issues,"project_id":contract.get("project_id"),"stage":stage,"route":route_name,"outline_contract_sha256":sha256(contract_path) if contract_path.is_file() else None,"issues":issues,"gates":{"outline_contract":not any(i["code"].startswith("outline_contract") or i["code"] in {"outline_approval_missing","required_artifact_missing","required_artifact_hash_mismatch"} for i in issues),"route":not any(i["code"].startswith("route_") or i["code"] in {"route_invalid","route_not_decided","visual_authority_mismatch","formal_content_not_ready","image_generation_requirement_missing","unexpected_image_generation_requirement"} for i in issues),"workflow":not any(i["code"].startswith("workflow_") for i in issues)}}
    if args.report: atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False)); return 0 if result["valid"] else 2


if __name__ == "__main__": raise SystemExit(main())
