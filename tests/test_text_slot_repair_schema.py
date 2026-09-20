#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "assets" / "schemas" / "text-slot-repair-plan.schema.json"


def main():
    data = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert data["properties"]["schema"]["const"] == "ai-ppt-plus/text-slot-repair-plan/v1"
    order = [item["const"] for item in data["properties"]["policy"]["properties"]["repair_order"]["prefixItems"]]
    assert order == ["slot_bbox", "text_margins", "reserved_icon_divider_space", "component_layout", "reference_line_topology", "line_spacing", "font_size_last"]
    assert data["properties"]["policy"]["properties"]["font_shrink_last"]["const"] is True
    assert data["properties"]["policy"]["properties"]["move_unrelated_objects"]["const"] is False
    print("text-slot repair schema tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
