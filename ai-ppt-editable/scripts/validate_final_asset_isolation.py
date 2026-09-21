#!/usr/bin/env python3
"""Block QA/debug/composite images from final authoring asset roots."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
FORBIDDEN_DIR_RE = re.compile(
    r"^(?:qa|debug|review|evidence|previews?|renders?|diffs?|comparisons?|"
    r"contact[-_ ]?sheets?|sprite[-_ ]?sheets?|montages?|composites?|"
    r"scratch|tmp|temp|debug[-_ ]?crops?|qa[-_ ]?crops?)$",
    re.IGNORECASE,
)
FORBIDDEN_FILE_RE = re.compile(
    r"(?:^|[-_. ])(?:contact[-_ ]?sheet|sprite[-_ ]?sheet|icon[-_ ]?sheet|"
    r"debug[-_ ]?crop|qa[-_ ]?crop|crop[-_ ]?debug|crop[-_ ]?qa|"
    r"side[-_ ]?by[-_ ]?side|comparison[-_ ]?montage|review[-_ ]?montage|"
    r"diff[-_ ]?map|heat[-_ ]?map|qa[-_ ]?composite|debug[-_ ]?composite)"
    r"(?:$|[-_. ])",
    re.IGNORECASE,
)


def _normalise_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _is_forbidden(path: Path, *, root: Path | None = None) -> tuple[bool, str | None]:
    candidate = path.resolve()
    parts = candidate.parts
    if root is not None:
        try:
            parts = candidate.relative_to(root.resolve()).parts
        except ValueError:
            pass
    for part in parts[:-1]:
        if FORBIDDEN_DIR_RE.fullmatch(part):
            return True, f"forbidden_directory:{part}"
    if FORBIDDEN_FILE_RE.search(candidate.name):
        return True, f"forbidden_filename:{candidate.name}"
    return False, None


def _asset_source(spec: dict[str, Any]) -> str | None:
    for key in ("file", "path", "source_path", "image"):
        value = spec.get(key)
        if isinstance(value, str) and value.strip():
            return value
    source = spec.get("source")
    if isinstance(source, dict):
        for key in ("path", "file"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return None


def _referenced_assets(deck: dict[str, Any], assets_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for slide_index, slide in enumerate(deck.get("slides") or [], 1):
        if not isinstance(slide, dict):
            continue
        for field in ("background", "frame"):
            raw = slide.get(field)
            if isinstance(raw, str) and raw.strip():
                path = Path(raw)
                resolved = (path if path.is_absolute() else assets_dir / path).resolve()
                records.append({"slide": slide_index, "kind": field, "object_id": slide.get(f"{field}_object_id") or field, "raw": raw, "path": str(resolved)})
        for collection, kind in (("panels", "panel"), ("icons", "icon")):
            for index, spec in enumerate(slide.get(collection) or [], 1):
                if not isinstance(spec, dict):
                    continue
                raw = _asset_source(spec)
                if not raw:
                    continue
                path = Path(raw)
                resolved = (path if path.is_absolute() else assets_dir / path).resolve()
                records.append({"slide": slide_index, "kind": kind, "object_id": spec.get("object_id") or spec.get("name") or f"{kind}-{index}", "raw": raw, "path": str(resolved)})
    return records


def validate_deck_asset_isolation(deck: dict[str, Any], layout_path: Path, *, scan_tree: bool = True) -> dict[str, Any]:
    layout_path = layout_path.resolve()
    raw_assets_dir = deck.get("assets_dir")
    explicit_assets_dir = deck.get("_assets_dir_explicit") is True or (
        "_assets_dir_explicit" not in deck and isinstance(raw_assets_dir, str) and bool(raw_assets_dir.strip())
    )
    assets_dir = _normalise_path(raw_assets_dir) if explicit_assets_dir else layout_path.parent.resolve()
    errors: list[dict[str, Any]] = []
    references = _referenced_assets(deck, assets_dir)

    # The root itself is a directory, so check its basename directly instead of
    # passing it through _is_forbidden(), which intentionally treats the final
    # path component as a filename.
    if FORBIDDEN_DIR_RE.fullmatch(assets_dir.name):
        errors.append({
            "code": "final_asset_root_is_qa_directory",
            "assets_dir": str(assets_dir),
            "reason": f"forbidden_directory:{assets_dir.name}",
        })

    for record in references:
        forbidden, reason = _is_forbidden(Path(record["path"]), root=assets_dir)
        if forbidden:
            errors.append({"code": "qa_asset_referenced_by_deck", "reason": reason, **record})

    scanned = 0
    forbidden_inventory: list[dict[str, str]] = []
    # Inventory scans are safe only for a declared final-asset root. When a
    # legacy layout omits assets_dir, its project root may legitimately also
    # contain QA evidence; explicit referenced QA paths are still blocked.
    effective_tree_scan = bool(scan_tree and explicit_assets_dir)
    if effective_tree_scan and assets_dir.is_dir():
        for path in sorted(assets_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            scanned += 1
            forbidden, reason = _is_forbidden(path, root=assets_dir)
            if forbidden:
                forbidden_inventory.append({"path": str(path.resolve()), "reason": str(reason)})
        if forbidden_inventory:
            errors.append({
                "code": "qa_assets_co_located_with_final_assets",
                "assets_dir": str(assets_dir),
                "count": len(forbidden_inventory),
                "files": forbidden_inventory,
            })

    return {
        "schema": "ai-ppt-plus/final-asset-isolation/v1",
        "valid": not errors,
        "layout": str(layout_path),
        "assets_dir": str(assets_dir),
        "scan_tree": effective_tree_scan,
        "assets_dir_explicit": explicit_assets_dir,
        "referenced_asset_count": len(references),
        "scanned_image_count": scanned,
        "references": references,
        "forbidden_inventory": forbidden_inventory,
        "errors": errors,
        "policy": {
            "final_assets_must_be_physically_separate_from_qa": True,
            "contact_sheets_authorable": False,
            "debug_crops_authorable": False,
            "qa_composites_authorable": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--no-tree-scan", action="store_true", help="Only inspect assets explicitly referenced by the deck.")
    args = parser.parse_args()
    layout = args.layout.resolve()
    try:
        deck = json.loads(layout.read_text(encoding="utf-8"))
        if not isinstance(deck, dict):
            raise TypeError("layout must be a JSON object")
        report = validate_deck_asset_isolation(deck, layout, scan_tree=not args.no_tree_scan)
    except Exception as exc:
        report = {"schema": "ai-ppt-plus/final-asset-isolation/v1", "valid": False, "errors": [{"code": "asset_isolation_validation_failed", "message": str(exc)}]}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
