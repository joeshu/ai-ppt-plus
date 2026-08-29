#!/usr/bin/env python3
"""Prove that the discovered authoring backend matches the routing contract."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from atomic_output import atomic_write_json


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def validate(environment_path: Path, contract_path: Path, skill_dir: Path | None = None) -> dict:
    environment = _read(environment_path)
    contract = _read(contract_path)
    root = skill_dir.resolve() if skill_dir else contract_path.resolve().parent.parent
    issues: list[dict] = []
    binding = (contract.get("bindings") or {}).get("authoring")
    if not isinstance(binding, dict):
        issues.append({"severity": "blocker", "code": "authoring_binding_missing"})
        binding = {}
    expected_backend = binding.get("backend")
    observed_backend = ((environment.get("selection") or {}).get("authoring_backend"))
    if expected_backend != observed_backend:
        issues.append({"severity": "blocker", "code": "authoring_backend_mismatch", "expected": expected_backend, "observed": observed_backend})

    checked_paths = []
    for field in ("entrypoint", "font_postprocessor"):
        value = binding.get(field)
        if not isinstance(value, str) or not value.strip():
            issues.append({"severity": "blocker", "code": "authoring_binding_path_missing", "field": field})
            continue
        path = (root / value).resolve()
        checked_paths.append({"field": field, "declared": value, "path": str(path), "exists": path.is_file()})
        if not path.is_file():
            issues.append({"severity": "blocker", "code": "authoring_binding_path_missing", "field": field, "path": str(path)})

    module = ((environment.get("capabilities") or {}).get("python_pptx") or {})
    if expected_backend == "python-pptx" and module.get("available") is not True:
        issues.append({"severity": "blocker", "code": "python_pptx_unavailable"})

    selection_reason = ((environment.get("selection") or {}).get("authoring_backend_reason"))
    return {
        "schema": "ai-ppt-plus/backend-binding-validation/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "environment": str(environment_path.resolve()),
        "environment_sha256": hashlib.sha256(environment_path.read_bytes()).hexdigest(),
        "contract": str(contract_path.resolve()),
        "binding": binding,
        "observed_backend": observed_backend,
        "selection_reason": selection_reason,
        "checked_paths": checked_paths,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment")
    parser.add_argument("contract")
    parser.add_argument("--skill-dir")
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        result = validate(Path(args.environment).resolve(), Path(args.contract).resolve(), Path(args.skill_dir).resolve() if args.skill_dir else None)
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/backend-binding-validation/v1", "valid": False, "status": "invalid", "issues": [{"severity": "blocker", "code": "runtime_error", "message": f"{type(exc).__name__}: {exc}"}]}
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("valid") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
