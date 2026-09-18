#!/usr/bin/env python3
"""Keep final icon asset directories free of contact sheets and QA composites."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

PATTERNS = ("contact_sheet", "contact-sheet", "contactsheet", "sprite_sheet", "sprite-sheet")


def is_composite(path: Path) -> bool:
    name = path.name.casefold()
    return any(pattern in name for pattern in PATTERNS)


def curate(asset_dir: Path, quarantine_dir: Path) -> dict:
    asset_dir = asset_dir.resolve()
    quarantine_dir = quarantine_dir.resolve()
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    moved = []
    for path in sorted(asset_dir.iterdir()):
        if not path.is_file() or not is_composite(path):
            continue
        target = quarantine_dir / path.name
        if target.exists():
            target.unlink()
        shutil.move(str(path), str(target))
        moved.append({"from": str(path), "to": str(target)})
    remaining = [str(path) for path in sorted(asset_dir.iterdir()) if path.is_file() and is_composite(path)]
    return {"schema": "ai-ppt-plus/icon-asset-curation/v1", "valid": not remaining, "asset_dir": str(asset_dir), "quarantine_dir": str(quarantine_dir), "moved_count": len(moved), "moved": moved, "remaining_composites": remaining}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset_dir", type=Path)
    parser.add_argument("--quarantine-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = curate(args.asset_dir, args.quarantine_dir)
    except Exception as exc:
        print(json.dumps({"schema": "ai-ppt-plus/icon-asset-curation/v1", "valid": False, "status": "blocked", "code": "icon_asset_curation_failed", "message": str(exc)}, ensure_ascii=False))
        return 2
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["valid"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
