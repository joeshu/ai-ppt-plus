#!/usr/bin/env python3
"""Delegate visual incumbent selection to the bundled editable worker."""
from __future__ import annotations

import importlib.util
from pathlib import Path


IMPLEMENTATION = Path(__file__).resolve().parents[1] / "ai-ppt-editable" / "scripts" / "select_visual_incumbent.py"
spec = importlib.util.spec_from_file_location("ai_ppt_editable_select_visual_incumbent", IMPLEMENTATION)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

load = module.load
score = module.score
regional_scores = module.regional_scores
select = module.select
main = module.main


if __name__ == "__main__":
    raise SystemExit(main())
