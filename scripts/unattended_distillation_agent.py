#!/usr/bin/env python3
"""Compatibility tombstone for the retired distillation subsystem."""
import sys

print("unattended distillation has been retired; use the normal deterministic QA/Repair Trace workflow", file=sys.stderr)
raise SystemExit(2)
