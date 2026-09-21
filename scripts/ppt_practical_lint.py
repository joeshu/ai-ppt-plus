#!/usr/bin/env python3
"""Root delegate for editable-worker practical PowerPoint lint."""
from __future__ import annotations

import runpy
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "ai-ppt-editable" / "scripts" / "ppt_practical_lint.py"
runpy.run_path(str(TARGET), run_name="__main__")
