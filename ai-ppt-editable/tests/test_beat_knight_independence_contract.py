#!/usr/bin/env python3
"""Competitive A/B must not accept a Knight baseline cloned from candidate structure."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    # This regression fixture records the concrete PR41 contamination signature:
    # candidate and purported Knight outputs had the exact same ordered
    # shape/geometry/text fingerprint, so they cannot establish independent
    # authoring provenance even though their media payloads differed.
    audit = ROOT / "evals" / "pr41-render-driven-20260919" / "r16-knight-independence-audit.json"
    payload = json.loads(audit.read_text(encoding="utf-8"))
    assert payload["checks"]["same_structural_fingerprint"] is True
    assert payload["checks"]["media_all_same"] is False
    assert payload["decision"] == "reject_as_independent_knight_baseline"
    assert "independently authored Knight baseline" in payload["reason"]
    assert "Knight-native authoring provenance" in payload["required_next"]
    print("Beat-Knight independent provenance regression: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
