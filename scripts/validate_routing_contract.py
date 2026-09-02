#!/usr/bin/env python3
"""Validate the executable ownership and backend routing contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/skill-routing/v1"
EXPECTED_NAMES = {"ai-ppt-plus", "ai-ppt-visual-gen", "ai-ppt-editable"}
REQUIRED_OWNS = {
    "ai-ppt-plus": {"intake", "source-authority", "narrative", "approved-outline", "route", "design-system", "manifest-reconciliation", "qa-aggregation", "reports", "human-closeout", "release-gates"},
    "ai-ppt-visual-gen": {"visual-generation-plan", "visual-prompt-contract", "raster-visual-generation", "single-slide-retry", "generated-source-retention", "deck-strip-review"},
    "ai-ppt-editable": {"reference-decomposition", "editable-layer-plan", "image-to-pptx-object-mapping", "pptx-authoring", "pptx-rendering", "technical-qa"},
}
REQUIRED_FORBIDS = {
    "ai-ppt-plus": {"silent-backend-substitution", "human-signoff-claim"},
    "ai-ppt-visual-gen": {"narrative-authority", "formal-text-authority", "image-to-editable-pptx", "release-eligibility", "human-signoff"},
    "ai-ppt-editable": {"narrative-redesign", "release-eligibility", "human-signoff"},
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", nargs="?", default=str(Path(__file__).resolve().parents[1] / "assets" / "skill-routing.template.json"))
    parser.add_argument("--report")
    args = parser.parse_args()
    path = Path(args.contract).resolve()
    issues: list[dict] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        data = {}
        issues.append({"severity": "blocker", "code": "routing_contract_unreadable", "message": f"{type(exc).__name__}: {exc}"})

    if data.get("schema") != SCHEMA:
        issues.append({"severity": "blocker", "code": "routing_schema_invalid", "observed": data.get("schema")})
    if data.get("orchestrator") != "ai-ppt-plus":
        issues.append({"severity": "blocker", "code": "routing_orchestrator_invalid", "observed": data.get("orchestrator")})
    skills = data.get("skills")
    if not isinstance(skills, list):
        skills = []
        issues.append({"severity": "blocker", "code": "routing_skills_not_array"})
    by_name: dict[str, dict] = {}
    for index, item in enumerate(skills):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item.get("name"):
            issues.append({"severity": "blocker", "code": "routing_skill_invalid", "index": index})
            continue
        name = item["name"]
        if name in by_name:
            issues.append({"severity": "blocker", "code": "routing_skill_duplicate", "name": name})
        by_name[name] = item
        owns = set(item.get("owns") or []) if isinstance(item.get("owns"), list) else set()
        forbids = set(item.get("forbids") or []) if isinstance(item.get("forbids"), list) else set()
        overlap = sorted(owns & forbids)
        if overlap:
            issues.append({"severity": "blocker", "code": "routing_owns_forbids_overlap", "name": name, "values": overlap})
        for value in sorted(REQUIRED_OWNS.get(name, set()) - owns):
            issues.append({"severity": "blocker", "code": "routing_ownership_missing", "name": name, "value": value})
        for value in sorted(REQUIRED_FORBIDS.get(name, set()) - forbids):
            issues.append({"severity": "blocker", "code": "routing_forbid_missing", "name": name, "value": value})
    if set(by_name) != EXPECTED_NAMES:
        issues.append({"severity": "blocker", "code": "routing_skill_set_invalid", "expected": sorted(EXPECTED_NAMES), "observed": sorted(by_name)})

    fallback_policy = data.get("fallback_policy")
    expected_fallback_policy = {
        "schema": "ai-ppt-plus/fallback-policy/v1",
        "primary_engine": "ai-ppt-editable",
        "fallback_engine": "GordenImage2PPTX",
        "fallback_scope": "region-only",
        "allow_full_page": False,
        "requires_explicit_reason": True,
        "requires_asset_record": True,
        "requires_user_decision_on_generation_failure": True,
        "forbidden_roles": {"formal-text", "semantic-panel", "panel-frame", "table", "chart", "card-frame", "whole-slide", "whole-page", "framework"},
    }
    if not isinstance(fallback_policy, dict):
        issues.append({"severity": "blocker", "code": "fallback_policy_missing"})
        fallback_policy = {}
    for key, expected in expected_fallback_policy.items():
        observed = fallback_policy.get(key)
        if key == "forbidden_roles":
            if set(observed or []) != expected:
                issues.append({"severity": "blocker", "code": "fallback_policy_mismatch", "field": key, "expected": sorted(expected), "observed": observed})
        elif observed != expected:
            issues.append({"severity": "blocker", "code": "fallback_policy_mismatch", "field": key, "expected": expected, "observed": observed})

    bindings = data.get("bindings")
    if not isinstance(bindings, dict):
        issues.append({"severity": "blocker", "code": "routing_bindings_missing"})
        bindings = {}
    expected_bindings = {
        "orchestrator": {"skill": "ai-ppt-plus", "entrypoint": "scripts/run_pipeline.py"},
        "reconstruction": {
            "skill": "ai-ppt-editable",
            "invocation": "sibling-skill",
            "skill_entrypoint": "ai-ppt-editable/SKILL.md",
            "runtime_entrypoint": "ai-ppt-editable/scripts/compose_pptx.py",
            "required_for": ["reference-reconstruction", "editable-pptx", "native-authoring"],
        },
        "visual_generation": {
            "skill": "ai-ppt-visual-gen",
            "invocation": "sibling-skill",
            "skill_entrypoint": "ai-ppt-visual-gen/SKILL.md",
            "runtime_entrypoint": "ai-ppt-visual-gen/scripts/run_visual_pipeline.py",
            "required_for": ["visual-creation:image-slide"],
            "tool_resolution": "runtime-discovery",
            "preferred_tool": "imagegen",
            "backend_policy": "raster-only",
            "source_retention": "generated-source-and-project-copy",
            "prompt_contract": "ai-ppt-plus/visual-generation-plan/v1",
        },
        "authoring": {"kind": "adapter", "backend": "python-pptx", "entrypoint": "ai-ppt-editable/scripts/authoring_backend.py", "font_postprocessor": "ai-ppt-editable/scripts/embed_fonts.py"},
    }
    for section, expected in expected_bindings.items():
        observed = bindings.get(section)
        if not isinstance(observed, dict):
            issues.append({"severity": "blocker", "code": "routing_binding_missing", "section": section})
            continue
        for key, value in expected.items():
            if observed.get(key) != value:
                issues.append({"severity": "blocker", "code": "routing_binding_mismatch", "section": section, "field": key, "expected": value, "observed": observed.get(key)})

    # A declaration is not executable unless every sibling skill and its own
    # self-contained runtime entrypoint is present in the repository bundle.
    skill_root = path.parent.parent
    for section, fields in {
        "orchestrator": ("entrypoint",),
        "visual_generation": ("skill_entrypoint", "runtime_entrypoint"),
        "reconstruction": ("skill_entrypoint", "runtime_entrypoint"),
        "authoring": ("entrypoint", "font_postprocessor"),
    }.items():
        binding = bindings.get(section) if isinstance(bindings, dict) else None
        if not isinstance(binding, dict):
            continue
        for field in fields:
            value = binding.get(field)
            if not isinstance(value, str) or not value.strip():
                continue
            target = (skill_root / value).resolve()
            if not target.is_file():
                issues.append({"severity": "blocker", "code": "routing_entrypoint_missing", "section": section, "field": field, "path": str(target)})

    result = {
        "schema": "ai-ppt-plus/routing-contract-validation/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "contract": str(path),
        "issues": issues,
        "bindings": bindings,
        "fallback_policy": fallback_policy,
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
