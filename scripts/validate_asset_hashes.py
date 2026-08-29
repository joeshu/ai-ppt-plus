#!/usr/bin/env python3
"""Validate declared SHA-256 provenance for files referenced by manifests.

This is the project-wide hash gate.  Domain validators still own their
semantic rules (alpha, panel independence, image-generation evidence, and so
on); this validator owns one invariant: every referenced file has a current,
lowercase SHA-256 declaration when strict mode is enabled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/asset-hash-validation/v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PATH_KEYS = ("path", "asset_path", "file", "output_path", "copied_to")
HASH_KEYS = ("sha256", "asset_sha256", "path_sha256", "copied_to_sha256", "file_sha256")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(value: Any, manifest: Path, base: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip() or value.startswith("native:"):
        return None
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    # A manifest may explicitly carry path_base, but the project root is the
    # default for the checked-in manifests used by the pipeline.
    return (base / candidate).resolve()


def _records(data: Any) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(data, dict):
        return []
    records: list[tuple[str, dict[str, Any]]] = []
    seen: set[int] = set()
    for key in ("assets", "panels", "icons"):
        values = data.get(key)
        if isinstance(values, list):
            for index, item in enumerate(values, 1):
                if isinstance(item, dict):
                    records.append((f"{key}[{index}]", item))
                    seen.add(id(item))
    for key in ("background", "frame_raw"):
        item = data.get(key)
        if isinstance(item, dict) and id(item) not in seen:
            records.append((key, item))
    return records


def validate(manifests: list[Path], *, base: Path | None = None, require: bool = False) -> dict[str, Any]:
    root = (base or manifests[0].parent).resolve()
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []
    record_count = 0
    for manifest in manifests:
        manifest = manifest.resolve()
        if not manifest.is_file():
            issues.append({"severity": "blocker", "code": "manifest_missing", "manifest": str(manifest)})
            continue
        try:
            data = _read(manifest)
        except Exception as exc:
            issues.append({"severity": "blocker", "code": "manifest_unreadable", "manifest": str(manifest), "message": f"{type(exc).__name__}: {exc}"})
            continue
        records = _records(data)
        record_count += len(records)
        for label, item in records:
            path_value = next((item.get(key) for key in PATH_KEYS if item.get(key) not in (None, "")), None)
            if path_value is None:
                # Native vectors and inline assets have no filesystem hash to
                # verify; their semantic validators cover their own evidence.
                continue
            asset_path = _resolve(path_value, manifest, root)
            if asset_path is None:
                continue
            if not asset_path.is_file():
                severity = "blocker" if require or item.get("required_for_delivery") is True else "warning"
                target = issues if severity == "blocker" else warnings
                target.append({"severity": severity, "code": "asset_file_missing", "manifest": str(manifest), "record": label, "path": str(asset_path)})
                continue
            declared = next((item.get(key) for key in HASH_KEYS if item.get(key) not in (None, "")), None)
            observed = _sha256(asset_path)
            row = {"manifest": str(manifest), "record": label, "path": str(asset_path), "declared_sha256": declared, "observed_sha256": observed}
            checked.append(row)
            if not isinstance(declared, str):
                issue = {"severity": "blocker", "code": "asset_hash_missing", **row}
                (issues if require else warnings).append(issue if require else {**issue, "severity": "warning"})
            elif not SHA256_RE.fullmatch(declared):
                issues.append({"severity": "blocker", "code": "asset_hash_invalid", **row})
            elif declared != observed:
                issues.append({"severity": "blocker", "code": "asset_hash_mismatch", **row})
    return {
        "schema": SCHEMA,
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "strict": require,
        "manifests": [str(path.resolve()) for path in manifests],
        "record_count": record_count,
        "checked_count": len(checked),
        "checked": checked,
        "issues": issues,
        "warnings": warnings,
        "human_visual_review_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", help="one or more JSON asset manifests")
    parser.add_argument("--base", help="project root used to resolve relative asset paths")
    parser.add_argument("--require", action="store_true", help="missing hashes are blockers")
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        result = validate([Path(value) for value in args.manifests], base=Path(args.base) if args.base else None, require=args.require)
    except Exception as exc:
        result = {"schema": SCHEMA, "valid": False, "status": "invalid", "issues": [{"severity": "blocker", "code": "runtime_error", "message": f"{type(exc).__name__}: {exc}"}], "warnings": []}
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("valid") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
