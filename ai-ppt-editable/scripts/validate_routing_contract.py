#!/usr/bin/env python3
"""Validate the standalone editable-worker ownership and authoring binding."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from atomic_output import atomic_write_json


REQUIRED_OWNS = {
    "reference-decomposition",
    "editable-layer-plan",
    "image-to-pptx-object-mapping",
    "pptx-authoring",
    "pptx-rendering",
    "technical-qa",
}
REQUIRED_FORBIDS = {"narrative-redesign", "release-eligibility", "human-signoff"}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", nargs="?", default=str(root / "assets" / "skill-routing.template.json"))
    parser.add_argument("--report")
    args = parser.parse_args()
    path = Path(args.contract).resolve()
    issues: list[dict] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        data = {}
        issues.append({"severity": "blocker", "code": "routing_contract_unreadable", "message": f"{type(exc).__name__}: {exc}"})
    if data.get("schema") != "ai-ppt-editable/skill-routing/v1":
        issues.append({"severity": "blocker", "code": "routing_schema_invalid", "observed": data.get("schema")})
    if data.get("skill") != "ai-ppt-editable":
        issues.append({"severity": "blocker", "code": "routing_skill_invalid", "observed": data.get("skill")})
    owns = set(data.get("owns") or [])
    forbids = set(data.get("forbids") or [])
    for value in sorted(REQUIRED_OWNS - owns):
        issues.append({"severity": "blocker", "code": "routing_ownership_missing", "value": value})
    for value in sorted(REQUIRED_FORBIDS - forbids):
        issues.append({"severity": "blocker", "code": "routing_forbid_missing", "value": value})
    if owns & forbids:
        issues.append({"severity": "blocker", "code": "routing_owns_forbids_overlap", "values": sorted(owns & forbids)})
    authoring = ((data.get("bindings") or {}).get("authoring"))
    expected = {
        "kind": "adapter",
        "backend": "python-pptx",
        "entrypoint": "scripts/authoring_backend.py",
        "font_postprocessor": "scripts/embed_fonts.py",
    }
    if not isinstance(authoring, dict):
        issues.append({"severity": "blocker", "code": "authoring_binding_missing"})
        authoring = {}
    for field, value in expected.items():
        if authoring.get(field) != value:
            issues.append({"severity": "blocker", "code": "authoring_binding_mismatch", "field": field, "expected": value, "observed": authoring.get(field)})
    for field in ("entrypoint", "font_postprocessor"):
        value = authoring.get(field)
        if isinstance(value, str) and not (root / value).is_file():
            issues.append({"severity": "blocker", "code": "authoring_entrypoint_missing", "field": field, "path": value})
    result = {
        "schema": "ai-ppt-editable/routing-validation/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "contract": str(path),
        "issues": issues,
        "bindings": data.get("bindings", {}),
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
