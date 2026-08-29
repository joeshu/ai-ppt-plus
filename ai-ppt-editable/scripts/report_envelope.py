#!/usr/bin/env python3
"""Helpers for the common technical/human/release report vocabulary."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "ai-ppt-plus/report-envelope/v1"
STATUSES = {"passed", "degraded", "failed", "needs-human-review", "invalid", "missing"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def standard_status(report: dict[str, Any], *, valid: bool | None = None, required: bool = True) -> str:
    """Map historical child statuses to the project-level vocabulary."""
    if valid is None:
        valid = report.get("valid") if isinstance(report.get("valid"), bool) else report.get("ok") if isinstance(report.get("ok"), bool) else None
    native = str(report.get("status") or "").strip().lower()
    if valid is False:
        return "failed"
    if native in {"unavailable", "needs-human-confirmation", "pending", "manual_required", "diagnostic"}:
        return "needs-human-review"
    if valid is True:
        return "passed" if native not in {"degraded", "warning"} else "degraded"
    return "failed" if required else "missing"


def normalize_child(
    report_type: str,
    path: Path,
    report: dict[str, Any] | None,
    *,
    required: bool,
    stage: str | None,
    deck_sha256: str | None,
) -> dict[str, Any]:
    """Return one stable evidence row without destroying native report detail."""
    resolved = path.resolve()
    present = resolved.is_file()
    report = report if isinstance(report, dict) else {}
    valid = report.get("valid") if isinstance(report.get("valid"), bool) else report.get("ok") if isinstance(report.get("ok"), bool) else None
    technical_valid = report.get("technical_valid") if isinstance(report.get("technical_valid"), bool) else valid is True
    human_required = report.get("human_visual_review_required")
    if not isinstance(human_required, bool):
        human_required = report.get("requires_human_closeout") if isinstance(report.get("requires_human_closeout"), bool) else True
    release_eligible = report.get("release_eligible") if isinstance(report.get("release_eligible"), bool) else False
    observed_deck_hash = report.get("deck_sha256")
    return {
        "report_type": report_type,
        "stage": stage,
        "required": required,
        "present": present,
        "valid": valid if present else False,
        "technical_valid": technical_valid if present else False,
        "status": standard_status(report, valid=valid, required=required) if present else "missing",
        "native_status": report.get("status"),
        "human_review_required": human_required,
        "human_review_status": "pending" if human_required else "not-required",
        "release_eligible": release_eligible,
        "issues": report.get("issues", report.get("errors", [])) if present else [{"code": "report_missing"}],
        "source": {
            "path": str(resolved),
            "sha256": sha256(resolved) if present else None,
            "deck_sha256": observed_deck_hash or deck_sha256,
        },
        "schema": report.get("schema"),
    }


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None
