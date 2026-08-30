#!/usr/bin/env python3
"""Validate a probe report against the checked-in environment contract."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/environment-validation/v1"


def version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split(".")[:3])
    except (AttributeError, ValueError):
        return ()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", default=str(Path(__file__).resolve().parents[1] / "assets" / "environment-contract.json"))
    parser.add_argument("--report", required=True, help="environment-report.json produced by probe_environment.py")
    parser.add_argument("--output")
    args = parser.parse_args()
    issues: list[dict] = []
    try:
        contract = json.loads(Path(args.contract).resolve().read_text(encoding="utf-8"))
        report = json.loads(Path(args.report).resolve().read_text(encoding="utf-8"))
    except Exception as exc:
        result = {"schema": SCHEMA, "valid": False, "status": "blocked", "issues": [{"severity": "blocker", "code": "environment_input_unreadable", "message": f"{type(exc).__name__}: {exc}"}]}
        if args.output:
            atomic_write_json(Path(args.output).resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 2
    if not isinstance(contract, dict) or contract.get("schema") != "ai-ppt-plus/environment-contract/v1":
        issues.append({"severity": "blocker", "code": "environment_contract_schema_invalid"})
    if not isinstance(report, dict) or not isinstance(report.get("capabilities"), dict):
        issues.append({"severity": "blocker", "code": "environment_report_capabilities_missing"})
        capabilities = {}
    else:
        capabilities = report["capabilities"]
    python_rule = contract.get("python", {}) if isinstance(contract, dict) else {}
    observed_python = version_tuple(str(report.get("python", "")))
    minimum = version_tuple(str(python_rule.get("minimum", "0")))
    maximum = version_tuple(str(python_rule.get("maximum_exclusive", "999")))
    if not observed_python or observed_python < minimum or observed_python >= maximum:
        issues.append({"severity": "blocker", "code": "python_version_out_of_contract", "observed": report.get("python"), "minimum": python_rule.get("minimum"), "maximum_exclusive": python_rule.get("maximum_exclusive")})
    required = contract.get("required_capabilities", []) if isinstance(contract, dict) else []
    for name in required:
        capability = capabilities.get(name)
        if not isinstance(capability, dict) or capability.get("available") is not True:
            issues.append({"severity": "blocker", "code": "required_capability_unavailable", "capability": name, "observed": capability})
    if isinstance(contract, dict) and contract.get("requirements_file"):
        requirements_path = Path(args.contract).resolve().parent.parent / str(contract["requirements_file"])
        if not requirements_path.is_file():
            issues.append({"severity": "blocker", "code": "requirements_file_missing", "path": str(requirements_path)})
        elif contract.get("requirements_must_be_pinned") is True:
            unpinned = []
            for line in requirements_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                if "==" not in line:
                    unpinned.append(line)
            if unpinned:
                issues.append({"severity": "blocker", "code": "requirements_not_pinned", "entries": unpinned})
    result = {
        "schema": SCHEMA,
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "contract": str(Path(args.contract).resolve()),
        "environment_report": str(Path(args.report).resolve()),
        "python": report.get("python"),
        "required_capabilities": required,
        "requirements_file": str((Path(args.contract).resolve().parent.parent / str(contract.get("requirements_file"))).resolve()) if isinstance(contract, dict) and contract.get("requirements_file") else None,
        "issues": issues,
    }
    if args.output:
        atomic_write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
