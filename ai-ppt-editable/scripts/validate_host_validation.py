#!/usr/bin/env python3
"""Validate human Office/WPS host verification evidence for a PPTX."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/host-validation/v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HOSTS = {"powerpoint", "wps", "libreoffice"}
PROFILES = {"desktop", "ios"}
REQUIRED_CHECKS = ("opened", "layout", "typography", "overflow", "editability", "visual_fidelity")


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def validate(path: Path, deck: Path, expected_pages: int, *, strict: bool, required_profile: str | None = None) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    data = load(path)
    observed_hash = digest(deck) if deck.is_file() else None
    if data is None:
        issues.append({"severity": "blocker", "code": "host_validation_unreadable"})
        data = {}
    if data.get("schema") != SCHEMA:
        issues.append({"severity": "blocker", "code": "host_validation_schema_invalid", "observed": data.get("schema")})
    if data.get("status") != "passed":
        issues.append({"severity": "blocker", "code": "host_validation_not_passed", "observed": data.get("status")})
    host = data.get("host") if isinstance(data.get("host"), dict) else {}
    host_kind = str(host.get("kind") or "").strip().lower()
    profile = str(host.get("profile") or "").strip().lower()
    if host_kind not in HOSTS:
        issues.append({"severity": "blocker", "code": "host_kind_invalid", "observed": host_kind})
    if strict and host_kind not in {"powerpoint", "wps"}:
        issues.append({"severity": "blocker", "code": "office_or_wps_host_required", "observed": host_kind})
    if profile and profile not in PROFILES:
        issues.append({"severity": "blocker", "code": "host_profile_invalid", "observed": profile})
    if required_profile:
        if required_profile not in PROFILES:
            raise ValueError(f"unsupported required profile: {required_profile}")
        if profile != required_profile:
            issues.append({"severity": "blocker", "code": "host_profile_mismatch", "expected": required_profile, "observed": profile})
        if required_profile == "ios" and host_kind != "wps":
            issues.append({"severity": "blocker", "code": "ios_wps_host_required", "observed": host_kind})
    for field in ("reviewer", "confirmed_at"):
        if not isinstance(data.get(field), str) or not data.get(field, "").strip():
            issues.append({"severity": "blocker", "code": "host_validation_field_missing", "field": field})
    if not deck.is_file():
        issues.append({"severity": "blocker", "code": "host_validation_deck_missing", "path": str(deck)})
    declared_hash = data.get("deck_sha256")
    if not isinstance(declared_hash, str) or not SHA256_RE.fullmatch(declared_hash):
        issues.append({"severity": "blocker", "code": "host_validation_deck_hash_missing"})
    elif observed_hash and declared_hash != observed_hash:
        issues.append({"severity": "blocker", "code": "host_validation_deck_hash_mismatch", "expected": observed_hash, "observed": declared_hash})
    checked = data.get("checked_slides")
    if not isinstance(checked, list) or sorted(checked) != list(range(1, expected_pages + 1)):
        issues.append({"severity": "blocker", "code": "host_validation_slide_coverage_mismatch", "expected": list(range(1, expected_pages + 1)), "observed": checked})
    checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
    for field in REQUIRED_CHECKS:
        if checks.get(field) is not True:
            issues.append({"severity": "blocker", "code": "host_validation_check_failed", "check": field, "observed": checks.get(field)})
    if required_profile == "ios":
        mobile = data.get("mobile_differences") if isinstance(data.get("mobile_differences"), dict) else {}
        for field in ("font_substitution_reviewed", "line_wrap_reviewed"):
            if mobile.get(field) is not True:
                issues.append({"severity": "blocker", "code": "ios_difference_review_missing", "field": field})
    screenshots = data.get("screenshots")
    if strict:
        if not isinstance(screenshots, list) or len(screenshots) < expected_pages:
            issues.append({"severity": "blocker", "code": "host_validation_screenshots_missing", "expected": expected_pages, "observed": len(screenshots) if isinstance(screenshots, list) else 0})
        else:
            seen: set[int] = set()
            for item in screenshots:
                if not isinstance(item, dict):
                    issues.append({"severity": "blocker", "code": "host_validation_screenshot_invalid"})
                    continue
                slide = item.get("slide_no")
                seen.add(slide)
                screenshot = Path(str(item.get("path") or ""))
                if not screenshot.is_absolute():
                    screenshot = path.parent / screenshot
                if not screenshot.is_file():
                    issues.append({"severity": "blocker", "code": "host_validation_screenshot_missing", "slide": slide, "path": str(screenshot.resolve())})
                    continue
                declared = item.get("sha256")
                actual = digest(screenshot)
                if not isinstance(declared, str) or not SHA256_RE.fullmatch(declared) or declared != actual:
                    issues.append({"severity": "blocker", "code": "host_validation_screenshot_hash_mismatch", "slide": slide, "expected": actual, "observed": declared})
            if seen != set(range(1, expected_pages + 1)):
                issues.append({"severity": "blocker", "code": "host_validation_screenshot_coverage_mismatch", "expected": list(range(1, expected_pages + 1)), "observed": sorted(seen)})
    result = {
        "schema": SCHEMA,
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "strict": strict,
        "required_profile": required_profile,
        "host": host,
        "reviewer": data.get("reviewer"),
        "confirmed_at": data.get("confirmed_at"),
        "deck": str(deck.resolve()),
        "deck_sha256": observed_hash or declared_hash,
        "checked_slides": checked,
        "checks": checks,
        "mobile_differences": data.get("mobile_differences"),
        "issues": issues,
        "human_visual_review_required": True,
        "limitation": "host evidence records a declared manual verification; it cannot simulate opening PowerPoint or WPS",
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence")
    parser.add_argument("--deck", required=True)
    parser.add_argument("--expected-pages", type=int, required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--required-profile", choices=sorted(PROFILES))
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    result = validate(Path(args.evidence).resolve(), Path(args.deck).resolve(), args.expected_pages, strict=args.strict, required_profile=args.required_profile)
    atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
