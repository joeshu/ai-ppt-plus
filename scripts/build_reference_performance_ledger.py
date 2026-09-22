#!/usr/bin/env python3
from pathlib import Path
import runpy

TARGET = Path(__file__).resolve().parents[1] / "ai-ppt-editable" / "scripts" / "build_reference_performance_ledger.py"
runpy.run_path(str(TARGET), run_name="__main__")
