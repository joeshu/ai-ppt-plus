#!/usr/bin/env python3
"""Delegate execution-profile validation to the editable worker."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).resolve().parents[1] / "ai-ppt-editable" / "scripts" / "validate_execution_profile.py"), run_name="__main__")
