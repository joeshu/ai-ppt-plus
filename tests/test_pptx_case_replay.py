#!/usr/bin/env python3
"""Repository contract for the social-channel replay after binary fixture cleanup."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "ai-ppt-editable" / "evals" / "social-channel-commission-native-01.json"
REPLAY = ROOT / "scripts" / "replay_pptx_case.py"


def main() -> int:
    assert CASE.is_file(), "case specification must remain as structured regression evidence"
    assert REPLAY.is_file(), "replay implementation must remain available for runtime-generated decks"
    spec = json.loads(CASE.read_text(encoding="utf-8"))
    assert isinstance(spec, dict) and spec, "case specification must be non-empty JSON"

    # Generated PPTX files are intentionally not repository fixtures anymore.
    forbidden = [
        ROOT / "ai-ppt-editable/evals/fixtures/social-channel-commission-editable-1.pptx",
        ROOT / "ai-ppt-editable/evals/fixtures/social-channel-commission-native-01-candidate.pptx",
        ROOT / "evals/case-replay-social-01/optimized-pptx/social-channel-commission-native-01.pptx",
        ROOT / "evals/case-replay-social-01/source/social-channel-commission-editable-original.pptx",
        ROOT / "evals/case-replay-social-01/runs/candidate/mutation-smoke.pptx",
    ]
    assert not [path for path in forbidden if path.exists()], "generated PPTX artifacts must be rebuilt, not committed"

    replay_source = REPLAY.read_text(encoding="utf-8")
    assert "--source-pptx" in replay_source and "--deck" in replay_source
    assert "native-table" in replay_source
    print("social-channel replay repository contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
