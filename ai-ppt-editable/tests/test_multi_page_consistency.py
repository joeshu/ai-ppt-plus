#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reconstruction.multi_page_consistency import audit_multi_page_consistency


def main() -> int:
    deck = {
        "theme": {"font": "Noto Sans SC"},
        "consistency_rules": {"locked_roles": ["title"], "repeated_asset_roles": ["logo"]},
        "slides": [
            {"texts": [{"object_id": "t1", "role": "title", "x": .08, "y": .06, "size": 28, "font": "Noto Sans SC", "text": "A"}],
             "icons": [{"object_id": "l1", "role": "logo", "x": .9, "y": .05, "w": .06, "h": .04, "source_sha256": "abc"}]},
            {"texts": [{"object_id": "t2", "role": "title", "x": .08, "y": .06, "size": 28, "font": "Noto Sans SC", "text": "B"}],
             "icons": [{"object_id": "l2", "role": "logo", "x": .9, "y": .05, "w": .06, "h": .04, "source_sha256": "abc"}]},
        ],
    }
    ok = audit_multi_page_consistency(deck)
    assert ok["valid"], ok
    deck["slides"][1]["texts"][0]["size"] = 32
    deck["slides"][1]["icons"][0]["source_sha256"] = "different"
    bad = audit_multi_page_consistency(deck)
    assert not bad["valid"]
    kinds = {item["kind"] for item in bad["issues"]}
    assert {"text-size", "asset-source"}.issubset(kinds)
    print("multi-page consistency: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
