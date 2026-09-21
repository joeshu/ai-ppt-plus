#!/usr/bin/env python3
"""Delegate execution-budget validation to the editable worker."""
from pathlib import Path
import runpy,sys
target=Path(__file__).resolve().parents[1]/"ai-ppt-editable"/"scripts"/"validate_execution_budget.py"
sys.path.insert(0,str(target.parent)); runpy.run_path(str(target),run_name="__main__")
