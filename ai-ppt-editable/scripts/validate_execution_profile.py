#!/usr/bin/env python3
"""Validate an execution profile against the canonical runtime budgets."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from execution_profiles import PROFILES

def validate(data: dict) -> list[str]:
    name = str(data.get("profile") or "").lower()
    if name not in PROFILES:
        return [f"unknown execution profile: {name or '<missing>'}"]
    expected = PROFILES[name]
    supplied = data.get("budgets")
    if supplied != expected:
        return [f"profile budgets differ from canonical {name} contract"]
    return []

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("profile",type=Path); a=p.parse_args()
    errors=validate(json.loads(a.profile.read_text(encoding="utf-8")))
    print(json.dumps({"valid":not errors,"errors":errors},ensure_ascii=False))
    return 0 if not errors else 2
if __name__ == "__main__": raise SystemExit(main())
