#!/usr/bin/env python3
"""Resolve CJK fonts from the runtime environment instead of repository binaries."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from strict_layout_preflight import _font_has_cjk

FONT_SUFFIXES = {".ttf", ".otf", ".ttc"}
DEFAULT_CJK_FAMILIES = (
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "Microsoft YaHei",
    "PingFang SC",
    "HarmonyOS Sans SC",
    "WenQuanYi Zen Hei",
)
FONT_WEIGHT_STYLES = {400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold"}


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


def resolve_font_file(family: str, *, bold: bool = False, weight: int | None = None) -> Path | None:
    """Resolve one real runtime font file for measurement/registration."""
    family = str(family or "").strip() or DEFAULT_CJK_FAMILIES[0]
    target_weight = int(weight) if weight is not None else (700 if bold else 400)
    style = FONT_WEIGHT_STYLES.get(target_weight, "Bold" if target_weight >= 700 else "Regular")
    resolved = _fc_match_file(f"{family}:style={style}") or _fc_match_file(family)
    if resolved:
        return resolved
    windows = Path("C:/Windows/Fonts")
    aliases = {}
    if target_weight in {400, 700}:
        aliases = {
            "microsoft yahei": ("msyhbd.ttc" if target_weight == 700 else "msyh.ttc"),
            "微软雅黑": ("msyhbd.ttc" if target_weight == 700 else "msyh.ttc"),
        }
    filename = aliases.get(family.lower())
    candidate = windows / filename if filename else None
    return candidate.resolve() if candidate and candidate.is_file() else None


def resolve_family_files(family: str) -> list[Path]:
    result: list[Path] = []
    for weight in (400, 500, 600, 700):
        path = resolve_font_file(family, weight=weight)
        if path and path not in result:
            result.append(path)
    return result


def resolve_cjk_family(preferred: list[str] | tuple[str, ...] | None = None) -> tuple[str | None, list[Path]]:
    for family in preferred or DEFAULT_CJK_FAMILIES:
        files = resolve_family_files(family)
        if files and any(_font_has_cjk(path)[0] for path in files):
            return family, files
    return None, []


def runtime_font_evidence(family: str | None = None) -> dict:
    requested = family or DEFAULT_CJK_FAMILIES[0]
    files = resolve_family_files(requested)
    coverage = [{"path": str(path), "cjk_coverage_valid": _font_has_cjk(path)[0], "matched_probes": _font_has_cjk(path)[1]} for path in files]
    coverage_valid = any(item["cjk_coverage_valid"] for item in coverage)
    resolved_family = requested if coverage_valid else None
    if not coverage_valid and family is None:
        resolved_family, files = resolve_cjk_family()
        coverage = [{"path": str(path), "cjk_coverage_valid": _font_has_cjk(path)[0], "matched_probes": _font_has_cjk(path)[1]} for path in files]
        coverage_valid = any(item["cjk_coverage_valid"] for item in coverage)
    return {
        "schema": "ai-ppt-plus/runtime-font-evidence/v1",
        "requested_family": requested,
        "resolved_family": resolved_family,
        "files": [str(path) for path in files],
        "coverage": coverage,
        "runtime_managed": True,
        "repository_font_binary_required": False,
        "valid": coverage_valid,
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
