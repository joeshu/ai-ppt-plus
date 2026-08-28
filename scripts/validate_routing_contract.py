#!/usr/bin/env python3
"""Validate the executable ownership and backend routing contract."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/skill-routing/v1"
EXPECTED_NAMES = {"ai-ppt-plus", "GordenImage2PPTX", "Presentations"}
REQUIRED_OWNS = {
    "ai-ppt-plus": {"intake", "narrative", "route", "design-system", "manifests", "qa", "reports", "release-gates"},
    "GordenImage2PPTX": {"reference-decomposition", "editable-layer-plan", "image-to-pptx-object-mapping"},
    "Presentations": {"pptx-create", "pptx-edit", "pptx-render", "ooxml-package-operations"},
}
REQUIRED_FORBIDS = {
    "ai-ppt-plus": {"silent-backend-substitution", "human-signoff-claim"},
    "GordenImage2PPTX": {"narrative-redesign", "release-eligibility", "human-signoff"},
    "Presentations": {"narrative-authority", "editability-policy", "release-claim"},
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

    bindings = data.get("bindings")
    if not isinstance(bindings, dict):
        issues.append({"severity": "blocker", "code": "routing_bindings_missing"})
        bindings = {}
    expected_bindings = {
        "orchestrator": {"skill": "ai-ppt-plus", "entrypoint": "scripts/run_pipeline.py"},
        "reconstruction": {"skill": "GordenImage2PPTX", "invocation": "external-skill", "required_for": ["reference-reconstruction"]},
        "authoring": {"backend": "python-pptx", "entrypoint": "scripts/authoring_backend.py", "font_postprocessor": "scripts/embed_fonts.py"},
    }
    for section, expected in expected_bindings.items():
        observed = bindings.get(section)
        if not isinstance(observed, dict):
            issues.append({"severity": "blocker", "code": "routing_binding_missing", "section": section})
            continue
        for key, value in expected.items():
            if observed.get(key) != value:
                issues.append({"severity": "blocker", "code": "routing_binding_mismatch", "section": section, "field": key, "expected": value, "observed": observed.get(key)})

    result = {
        "schema": "ai-ppt-plus/routing-contract-validation/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "contract": str(path),
        "issues": issues,
        "bindings": bindings,
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
