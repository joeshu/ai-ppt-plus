#!/usr/bin/env python3
"""Resolve CJK fonts from the runtime environment instead of repository binaries."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

FONT_SUFFIXES = {".ttf", ".otf", ".ttc"}
DEFAULT_CJK_FAMILIES = (
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "Microsoft YaHei",
    "PingFang SC",
    "HarmonyOS Sans SC",
    "WenQuanYi Zen Hei",
)


def _fc_match_file(pattern: str) -> Path | None:
    tool = shutil.which("fc-match")
    if not tool:
        return None
    proc = subprocess.run([tool, "-f", "%{file}\n", pattern], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None
    for raw in proc.stdout.splitlines():
        path = Path(raw.strip())
        if path.is_file() and path.suffix.lower() in FONT_SUFFIXES:
            return path.resolve()
    return None


def resolve_font_file(family: str, *, bold: bool = False) -> Path | None:
    family = str(family or "").strip() or DEFAULT_CJK_FAMILIES[0]
    style = "Bold" if bold else "Regular"
    resolved = _fc_match_file(f"{family}:style={style}") or _fc_match_file(family)
    if resolved:
        return resolved
    windows = Path("C:/Windows/Fonts")
    aliases = {
        "microsoft yahei": ("msyhbd.ttc" if bold else "msyh.ttc"),
        "微软雅黑": ("msyhbd.ttc" if bold else "msyh.ttc"),
    }
    filename = aliases.get(family.lower())
    candidate = windows / filename if filename else None
    return candidate.resolve() if candidate and candidate.is_file() else None


def resolve_family_files(family: str) -> list[Path]:
    result: list[Path] = []
    for bold in (False, True):
        path = resolve_font_file(family, bold=bold)
        if path and path not in result:
            result.append(path)
    return result


def resolve_cjk_family(preferred: list[str] | tuple[str, ...] | None = None) -> tuple[str | None, list[Path]]:
    for family in preferred or DEFAULT_CJK_FAMILIES:
        files = resolve_family_files(family)
        if files:
            return family, files
    return None, []


def runtime_font_evidence(family: str | None = None) -> dict:
    requested = family or DEFAULT_CJK_FAMILIES[0]
    files = resolve_family_files(requested)
    resolved_family = requested if files else None
    if not files and family is None:
        resolved_family, files = resolve_cjk_family()
    return {
        "schema": "ai-ppt-plus/runtime-font-evidence/v1",
        "requested_family": requested,
        "resolved_family": resolved_family,
        "files": [str(path) for path in files],
        "runtime_managed": True,
        "repository_font_binary_required": False,
        "valid": bool(files),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = runtime_font_evidence(args.family)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
