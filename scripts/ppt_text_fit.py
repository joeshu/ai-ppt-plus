#!/usr/bin/env python3
"""Root runtime mirror for ai-ppt-editable/scripts/ppt_text_fit.py."""
from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "ai-ppt-editable" / "scripts" / "ppt_text_fit.py"),
    run_name="__main__",
)
