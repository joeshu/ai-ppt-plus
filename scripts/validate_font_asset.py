#!/usr/bin/env python3
"""Validate a task-local font file against its manifest.

This is deliberately separate from font discovery. ``probe_fonts.py`` answers
whether a family can be resolved; this script answers whether the declared
portable asset is the file that will actually be used and whether it covers a
small representative CJK smoke set.

Usage: validate_font_asset.py --font-dir project-fonts/ --report report.json
       [--manifest font-manifest.json] [--require-cjk]
"""

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from atomic_output import atomic_write_json


SMOKE_TEXT = "中文联通案例存量双终端优秀方案概述营销重点包装复盘"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def parse_charset(raw: str) -> set[int]:
    values: set[int] = set()
    for token in raw.split():
        if "-" in token:
            start, end = token.split("-", 1)
        else:
            start = end = token
        try:
            values.update(range(int(start, 16), int(end, 16) + 1))
        except ValueError:
            continue
    return values


def run_query(command: str | None, font: Path, fmt: str) -> tuple[str | None, str | None]:
    if not command:
        return None, f"{Path(font).name}: required fontconfig command is unavailable"
    try:
        completed = subprocess.run(
            [command, "-f", fmt, str(font)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if completed.returncode != 0:
        return None, completed.stderr.strip() or f"{command} failed with {completed.returncode}"
    return completed.stdout.strip(), None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", required=True)
    parser.add_argument("--manifest", help="manifest path; defaults to FONT_DIR/font-manifest.json")
    parser.add_argument("--report", required=True)
    parser.add_argument("--require-cjk", action="store_true")
    args = parser.parse_args()

    root = Path(args.font_dir).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else root / "font-manifest.json"
    issues: list[dict] = []
    warnings: list[dict] = []
    manifest: dict = {}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        issues.append({"severity": "blocker", "code": "font_manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"})

    declared_file = manifest.get("file") if isinstance(manifest, dict) else None
    font_path = (root / str(declared_file)).resolve() if declared_file else root / "<missing>"
    if not declared_file:
        issues.append({"severity": "blocker", "code": "font_file_missing_from_manifest"})
    elif not inside(root, font_path):
        issues.append({"severity": "blocker", "code": "font_path_outside_font_dir", "file": str(declared_file)})
    elif not font_path.is_file():
        issues.append({"severity": "blocker", "code": "font_file_missing", "file": str(font_path)})

    actual_hash = sha256(font_path) if font_path.is_file() else None
    expected_hash = manifest.get("sha256") if isinstance(manifest, dict) else None
    if expected_hash and actual_hash and expected_hash.lower() != actual_hash.lower():
        issues.append({"severity": "blocker", "code": "font_sha256_mismatch", "expected": expected_hash, "observed": actual_hash})
    elif not expected_hash:
        issues.append({"severity": "blocker", "code": "font_sha256_missing_from_manifest"})

    fc_scan = shutil.which("fc-scan")
    fc_query = shutil.which("fc-query")
    family = None
    charset_raw = None
    if font_path.is_file():
        family, error = run_query(fc_scan, font_path, "%{family}\\n")
        if error:
            issues.append({"severity": "blocker", "code": "font_scan_failed", "message": error})
        charset_raw, error = run_query(fc_query, font_path, "%{charset}\\n")
        if error:
            severity = "blocker" if args.require_cjk else "warning"
            (issues if severity == "blocker" else warnings).append({"severity": severity, "code": "font_charset_unavailable", "message": error})

    declared_family = str(manifest.get("family", "")).strip() if isinstance(manifest, dict) else ""
    if declared_family and family and declared_family.lower() not in family.lower():
        issues.append({"severity": "blocker", "code": "font_family_mismatch", "expected": declared_family, "observed": family})

    charset = parse_charset(charset_raw or "")
    missing_chars = sorted({char for char in SMOKE_TEXT if ord(char) not in charset})
    if missing_chars:
        severity = "blocker" if args.require_cjk else "warning"
        record = {"severity": severity, "code": "cjk_glyphs_missing", "characters": missing_chars}
        (issues if severity == "blocker" else warnings).append(record)
    elif args.require_cjk and not charset_raw:
        issues.append({"severity": "blocker", "code": "cjk_coverage_unverified"})

    if not manifest.get("license") or not manifest.get("license_url"):
        issues.append({"severity": "blocker", "code": "font_license_declaration_missing"})

    result = {
        "schema": "ai-ppt-plus/font-asset-validation/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "font_dir": str(root),
        "manifest": str(manifest_path),
        "file": str(font_path),
        "family": family,
        "declared_family": declared_family,
        "sha256": actual_hash,
        "expected_sha256": expected_hash,
        "cjk_smoke_text": SMOKE_TEXT,
        "cjk_coverage_verified": bool(charset_raw) and not missing_chars,
        "missing_cjk_characters": missing_chars,
        "issues": issues,
        "warnings": warnings,
        "embedding": manifest.get("embedding") if isinstance(manifest, dict) else None,
    }
    output = Path(args.report)
    atomic_write_json(output.resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
