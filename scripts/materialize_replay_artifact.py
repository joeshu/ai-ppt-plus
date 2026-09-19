#!/usr/bin/env python3
"""Materialize immutable replay artifacts stored as base64 text parts.

This keeps binary PPTX/image fixtures reviewable through text-only repository
connectors while reconstructing the exact approved bytes before a replay.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ai-ppt-plus/replay-artifact/v1"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def materialize(manifest_path: Path, output: Path) -> dict:
    manifest_path = manifest_path.resolve()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise ValueError(f"unsupported replay artifact schema: {data.get('schema')!r}")
    if data.get("encoding") != "base64-parts":
        raise ValueError(f"unsupported replay artifact encoding: {data.get('encoding')!r}")
    parts = data.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError("replay artifact parts must be a non-empty list")
    encoded = "".join((ROOT / str(part)).read_text(encoding="ascii").strip() for part in parts)
    raw = base64.b64decode(encoded, validate=True)
    observed = digest(raw)
    expected = str(data.get("sha256") or "")
    if expected and observed != expected:
        raise ValueError(f"artifact sha256 mismatch: expected={expected} observed={observed}")
    expected_size = data.get("size_bytes")
    if isinstance(expected_size, int) and len(raw) != expected_size:
        raise ValueError(f"artifact size mismatch: expected={expected_size} observed={len(raw)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    return {"valid": True, "manifest": str(manifest_path), "output": str(output), "sha256": observed, "size_bytes": len(raw)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = materialize(args.manifest, args.output)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
