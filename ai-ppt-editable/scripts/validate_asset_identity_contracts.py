#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PLAN_SCHEMA = "ai-ppt-plus/authoring-plan/v1"
CONTRACT_SCHEMA = "ai-ppt-plus/asset-identity-contract/v1"
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def issue(code: str, detail: str, object_id: str | None = None) -> dict:
    row = {"severity": "blocker", "code": code, "detail": detail}
    if object_id:
        row["object_id"] = object_id
    return row


def _nonempty_strings(value) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(x, str) and x.strip() for x in value)


def validate_contract(contract: object, object_id: str, source_sha: str | None) -> list[dict]:
    out: list[dict] = []
    if not isinstance(contract, dict):
        return [issue("asset_identity_contract_missing", "imagegen_asset requires asset_contract", object_id)]
    if contract.get("schema") != CONTRACT_SCHEMA:
        out.append(issue("asset_identity_schema_invalid", f"expected {CONTRACT_SCHEMA}", object_id))
    identity = contract.get("semantic_identity")
    if not isinstance(identity, dict) or not isinstance(identity.get("subject"), str) or not identity.get("subject", "").strip(): out.append(issue("asset_identity_subject_missing", "semantic_identity.subject is required", object_id))
    if not isinstance(identity, dict) or not _nonempty_strings(identity.get("must_preserve")): out.append(issue("asset_identity_traits_missing", "semantic_identity.must_preserve requires at least one trait", object_id))
    forbidden = identity.get("forbidden_substitutions") if isinstance(identity, dict) else None
    if not isinstance(forbidden, list) or not all(isinstance(x, str) and x.strip() for x in forbidden): out.append(issue("asset_identity_forbidden_invalid", "forbidden_substitutions must be a string list", object_id))
    if not _nonempty_strings(contract.get("contour_traits")): out.append(issue("asset_contour_traits_missing", "at least one contour trait is required", object_id))
    colors = contract.get("color_roles")
    if not isinstance(colors, list) or not colors: out.append(issue("asset_color_roles_missing", "at least one semantic color role is required", object_id))
    else:
        seen = set()
        for color in colors:
            if not isinstance(color, dict): out.append(issue("asset_color_role_invalid", "color role must be an object", object_id)); continue
            role = color.get("role"); value = color.get("hex")
            if not isinstance(role, str) or not role.strip() or role in seen: out.append(issue("asset_color_role_invalid", "color role names must be non-empty and unique", object_id))
            else: seen.add(role)
            if not isinstance(value, str) or not HEX_RE.match(value): out.append(issue("asset_color_hex_invalid", "color role hex must be #RRGGBB", object_id))
    alpha = contract.get("alpha")
    if not isinstance(alpha, dict) or alpha.get("required") is not True or alpha.get("transparent_edges") is not True: out.append(issue("asset_alpha_contract_invalid", "true alpha and transparent edges are required", object_id))
    else:
        padding = alpha.get("safe_padding_ratio")
        if not isinstance(padding, (int, float)) or not 0 <= float(padding) <= 0.35: out.append(issue("asset_safe_padding_invalid", "safe_padding_ratio must be within 0..0.35", object_id))
    provenance = contract.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("generation_required") is not True or provenance.get("source_crop_final_fallback") is not False: out.append(issue("asset_provenance_contract_invalid", "generation_required=true and source_crop_final_fallback=false are required", object_id))
    elif provenance.get("reference_sha256") is not None:
        ref_sha = str(provenance.get("reference_sha256"))
        if not SHA_RE.match(ref_sha): out.append(issue("asset_provenance_sha_invalid", "reference_sha256 must be SHA-256", object_id))
        elif source_sha and ref_sha.lower() != source_sha.lower(): out.append(issue("asset_provenance_sha_mismatch", "asset reference_sha256 must match AuthoringPlan source", object_id))
    return out


def validate(plan: dict) -> dict:
    issues: list[dict] = []
    if plan.get("schema") != PLAN_SCHEMA: issues.append(issue("asset_identity_plan_schema_invalid", f"expected {PLAN_SCHEMA}"))
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}; source_sha = source.get("sha256") if isinstance(source.get("sha256"), str) else None
    objects = plan.get("objects") if isinstance(plan.get("objects"), list) else []; imagegen = [o for o in objects if isinstance(o, dict) and o.get("implementation_type") == "imagegen_asset"]
    for obj in imagegen: issues.extend(validate_contract(obj.get("asset_contract"), str(obj.get("object_id") or ""), source_sha))
    return {"schema": "ai-ppt-plus/asset-identity-validation/v1", "valid": not issues, "status": "passed" if not issues else "failed", "imagegen_asset_count": len(imagegen), "issues": issues}


def main() -> int:
    p = argparse.ArgumentParser(description="Validate ImageGen asset color/identity contracts in AuthoringPlan."); p.add_argument("authoring_plan", type=Path); p.add_argument("--report", type=Path); p.add_argument("--json", action="store_true"); args = p.parse_args()
    try:
        plan = json.loads(args.authoring_plan.read_text(encoding="utf-8"))
        if not isinstance(plan, dict): raise ValueError("AuthoringPlan must be a JSON object")
        result = validate(plan)
    except Exception as exc: result = {"schema": "ai-ppt-plus/asset-identity-validation/v1", "valid": False, "status": "failed", "imagegen_asset_count": 0, "issues": [issue("asset_identity_plan_unreadable", str(exc))]}
    if args.report: args.report.parent.mkdir(parents=True, exist_ok=True); args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json or not args.report: print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__": raise SystemExit(main())
