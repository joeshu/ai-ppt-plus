#!/usr/bin/env python3
"""Discover local font files, families, weights and CJK coverage."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from atomic_output import atomic_write_json

try:
    from fontTools.ttLib import TTFont
except Exception:  # pragma: no cover
    TTFont = None

FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}
DEFAULT_FAMILIES = ["Noto Sans CJK SC", "Noto Sans SC", "WenQuanYi Zen Hei"]
CJK_PROBES = (0x4E2D, 0x6587, 0x8052, 0x901A, 0x70B9, 0x6570)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def name_value(font, name_id: int) -> str | None:
    if "name" not in font:
        return None
    for item in font["name"].names:
        if item.nameID == name_id:
            try:
                return item.toUnicode()
            except Exception:
                return None
    return None


def inspect_font(path: Path) -> dict:
    record = {"path": str(path.resolve()), "filename": path.name, "sha256": sha256(path),
              "family": None, "subfamily": None, "postscript": None, "weight": None,
              "style": None, "cjk": False, "cjk_missing": list(CJK_PROBES), "error": None}
    if TTFont is None:
        record["error"] = "fontTools unavailable"
        return record
    try:
        font = TTFont(str(path), fontNumber=0)
        record.update({"family": name_value(font, 1), "subfamily": name_value(font, 2),
                       "postscript": name_value(font, 6),
                       "weight": int(font["OS/2"].usWeightClass) if "OS/2" in font else None})
        cmap = set()
        for table in font["cmap"].tables:
            cmap.update(table.cmap.keys())
        missing = [code for code in CJK_PROBES if code not in cmap]
        record["cjk_missing"] = missing
        record["cjk"] = not missing
        record["style"] = "italic" if "italic" in (record.get("subfamily") or "").lower() else "normal"
        font.close()
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def candidate_dirs(explicit: list[str]) -> list[Path]:
    cwd = Path.cwd().resolve()
    values = [Path(item).expanduser() for item in explicit]
    values += [cwd / "assets" / "fonts", cwd / "fonts", cwd / "project-fonts",
               cwd / "ai-ppt-editable" / "assets" / "fonts"]
    result = []
    for value in values:
        value = value.resolve()
        if value.is_dir() and value not in result:
            result.append(value)
    return result


def license_status(dirs: list[Path]) -> dict:
    found = []
    for root in dirs:
        for path in root.iterdir():
            if path.is_file() and path.name.lower().split(".")[0] in {"license", "licence", "copying", "notice", "ofl"}:
                found.append(str(path))
    return {"status": "declared" if found else "unverified", "files": sorted(found)}


def fc_resolve(family: str, font_env: dict) -> str | None:
    tool = shutil.which("fc-match")
    if not tool:
        return None
    proc = subprocess.run([tool, "-f", "%{family}\n", family], capture_output=True, text=True, env=font_env)
    return proc.stdout.strip().splitlines()[0] if proc.returncode == 0 and proc.stdout.strip() else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", "-o", required=True)
    parser.add_argument("--font-dir", action="append", default=[])
    parser.add_argument("--font", action="append", default=[])
    parser.add_argument("--font-family-alias", help="registration family used by the renderer when files have distinct internal family names")
    parser.add_argument("--require-cjk", action="store_true")
    args = parser.parse_args()
    dirs = candidate_dirs(args.font_dir)
    paths = sorted({path.resolve() for root in dirs for path in root.rglob("*") if path.is_file() and path.suffix.lower() in FONT_EXTENSIONS})
    files = [inspect_font(path) for path in paths]
    families = sorted({item["family"] for item in files if item.get("family")})
    requested = args.font or families or DEFAULT_FAMILIES
    env = os.environ.copy()
    records = []
    for family in requested:
        matching = [item for item in files if str(item.get("family", "")).lower() == family.lower()]
        alias_files = [item for item in files if item.get("cjk")] if args.font_family_alias else []
        resolved = matching[0]["family"] if matching else (args.font_family_alias if alias_files else fc_resolve(family, env))
        local_files = matching or alias_files
        records.append({"requested": family, "resolved": resolved,
                        "registration_family": args.font_family_alias,
                        "exact_or_family_match": bool(matching) or bool(alias_files) or bool(resolved and family.lower() in resolved.lower()),
                        "local_files": [item["path"] for item in local_files],
                        "cjk_ready": any(item.get("cjk") for item in local_files)})
    cjk_ready = any(item.get("cjk") for item in files)
    weights = sorted({int(item["weight"]) for item in files if isinstance(item.get("weight"), int)})
    missing_weights = [weight for weight in (400, 500, 600, 700) if weight not in weights]
    output = {"schema": "ai-ppt-plus/font-report/v2", "ok": not (args.require_cjk and not cjk_ready),
              "generated_at": datetime.now(timezone.utc).isoformat(), "font_dirs": [str(path) for path in dirs],
              "font_files": files, "discovered_families": families, "requested": records,
              "registration_family": args.font_family_alias,
              "cjk_delivery_supported": cjk_ready, "weights_found": weights,
              "missing_weights": missing_weights, "simulated_bold_possible": 700 not in weights,
              "font_status": {"files_found": bool(files), "family_discovered": bool(families),
                              "glyph_route_available": cjk_ready, "license": license_status(dirs),
                              "render_review": "required", "silent_fallback": False},
              "rule": "Discovery is not render proof; actual renderer family and visible CJK smoke evidence must be recorded separately."}
    if not cjk_ready and args.require_cjk:
        output["error"] = "cjk_font_unresolved"
    atomic_write_json(Path(args.output).resolve(), output)
    print(json.dumps(output, ensure_ascii=False))
    return 0 if output["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
