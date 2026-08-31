#!/usr/bin/env python3
"""Validate structured human closeout sign-off.

Required boolean decisions are narrative, facts, visual, fidelity and brand.
An optional boolean `editability` decision records acceptance of L3/L4
reduced-editability or manual placeholders; it is never implicitly approved.
This validator never creates approval and never treats a missing field as an
implicit yes.
"""
import argparse
import hashlib
import json
from pathlib import Path
from atomic_output import atomic_write_json

REQUIRED = ("narrative", "facts", "visual", "fidelity", "brand")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("signoff")
    parser.add_argument("--report")
    parser.add_argument("--deck", help="bind human approval to the exact PPTX bytes")
    parser.add_argument("--strict-evidence", action="store_true", help="require reviewer, timestamp and exact deck SHA-256")
    args = parser.parse_args()
    path = Path(args.signoff)
    issues = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/signoff-validation/v1", "valid": False, "status": "invalid", "issues": [{"severity": "blocker", "code": "invalid_json", "message": f"{type(exc).__name__}: {exc}"}]}
        print(json.dumps(result, ensure_ascii=False))
        return 3
    if not isinstance(data, dict):
        issues.append({"severity": "blocker", "code": "signoff_not_object"})
        data = {}
    for field in REQUIRED:
        if field not in data:
            issues.append({"severity": "blocker", "code": "missing_decision", "field": field})
        elif not isinstance(data[field], bool):
            issues.append({"severity": "blocker", "code": "decision_not_boolean", "field": field})
        elif data[field] is not True:
            issues.append({"severity": "blocker", "code": "decision_not_approved", "field": field})
    decisions = {field: data.get(field) for field in REQUIRED}
    if "editability" in data:
        if not isinstance(data["editability"], bool):
            issues.append({"severity": "blocker", "code": "decision_not_boolean", "field": "editability"})
        decisions["editability"] = data["editability"]
    deck_path = Path(args.deck).resolve() if args.deck else None
    observed_deck_hash = sha256(deck_path) if deck_path and deck_path.is_file() else None
    declared_deck_hash = data.get("deck_sha256")
    if args.strict_evidence:
        if not isinstance(data.get("reviewer"), str) or not data.get("reviewer", "").strip():
            issues.append({"severity": "blocker", "code": "reviewer_missing"})
        if not isinstance(data.get("confirmed_at"), str) or not data.get("confirmed_at", "").strip():
            issues.append({"severity": "blocker", "code": "confirmed_at_missing"})
        if deck_path is None or not deck_path.is_file():
            issues.append({"severity": "blocker", "code": "signoff_deck_missing"})
        elif declared_deck_hash != observed_deck_hash:
            issues.append({"severity": "blocker", "code": "signoff_deck_hash_mismatch", "expected": observed_deck_hash, "observed": declared_deck_hash})
    elif observed_deck_hash is not None and declared_deck_hash is not None and declared_deck_hash != observed_deck_hash:
        issues.append({"severity": "blocker", "code": "signoff_deck_hash_mismatch", "expected": observed_deck_hash, "observed": declared_deck_hash})
    result = {
        "schema": "ai-ppt-plus/signoff-validation/v1",
        "valid": not issues,
        "status": "approved" if not issues else "incomplete",
        "reviewer": data.get("reviewer"),
        "confirmed_at": data.get("confirmed_at"),
        "signoff_sha256": sha256(path),
        "deck": str(deck_path) if deck_path else None,
        "deck_sha256": observed_deck_hash if observed_deck_hash is not None else declared_deck_hash,
        "decisions": decisions,
        "issues": issues,
    }
    if args.report:
        report = Path(args.report)
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
