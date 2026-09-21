#!/usr/bin/env python3
"""Delegate finalization preflight to the bundled editable worker."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


IMPLEMENTATION = Path(__file__).resolve().parents[1] / "ai-ppt-editable" / "scripts" / "validate_finalization_preflight.py"
sys.path.insert(0, str(IMPLEMENTATION.parent))
spec = importlib.util.spec_from_file_location("ai_ppt_editable_finalization_preflight", IMPLEMENTATION)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

validate = module.validate
main = module.main


if __name__ == "__main__":
    raise SystemExit(main())
