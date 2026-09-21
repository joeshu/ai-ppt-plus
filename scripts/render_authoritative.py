#!/usr/bin/env python3
"""Root delegate for the editable worker authoritative renderer."""
from __future__ import annotations

import runpy
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "ai-ppt-editable" / "scripts" / "render_authoritative.py"
runpy.run_path(str(TARGET), run_name="__main__")
