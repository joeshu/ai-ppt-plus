#!/usr/bin/env python3
"""Run the 12-case replay with reference-derived native layout overrides.

The legacy generic builders remain available as a control. Cases are migrated to
REFERENCE_BUILDERS one by one only after their reference structure is audited.
"""
from __future__ import annotations

import run_replay_suite as legacy
from reference_layouts import build_reference_layout


_ORIGINAL_BUILD_LAYOUT = legacy.build_layout


def reference_first_build_layout(case, run_dir, optimized):
    resolved = build_reference_layout(case, run_dir, optimized, legacy)
    if resolved is not None:
        return resolved
    return _ORIGINAL_BUILD_LAYOUT(case, run_dir, optimized)


legacy.build_layout = reference_first_build_layout


if __name__ == "__main__":
    raise SystemExit(legacy.main())
