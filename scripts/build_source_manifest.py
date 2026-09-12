#!/usr/bin/env python3
"""Write hash-bound provenance for a reproducible PPTX build."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from atomic_output import atomic_write_json


def record(path: str | None) -> dict:
    if not path: return {"path": None, "exists": False, "sha256": None}
    value = Path(path).resolve()
    return {"path": str(value), "exists": value.is_file(), "sha256": hashlib.sha256(value.read_bytes()).hexdigest() if value.is_file() else None, "size": value.stat().st_size if value.is_file() else None}


def load(path: str | None):
    if not path: return None
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception: return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--font", action="append", required=True)
    parser.add_argument("--asset", action="append", default=[])
    parser.add_argument("--build-script", required=True)
    parser.add_argument("--pptx", required=True)
    parser.add_argument("--qa-dir", required=True)
    parser.add_argument("--repo-sha", required=True)
    parser.add_argument("--render-report", required=True)
    parser.add_argument("--finalizer-receipt", required=True)
    parser.add_argument("--authoring-contract", required=True)
    parser.add_argument("--render-tool", required=True)
    parser.add_argument("--output", "-o", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    issues = []
    inputs = [record(path) for path in args.input]
    fonts = [record(path) for path in args.font]
    assets = [record(path) for path in args.asset]
    for group_name, group in (("inputs", inputs), ("fonts", fonts), ("assets", assets), ("build_script", [record(args.build_script)]), ("pptx", [record(args.pptx)])):
        for item in group:
            if not item["exists"]: issues.append({"severity": "blocker", "code": "source_file_missing", "group": group_name, "path": item["path"]})
    qa_dir = Path(args.qa_dir).resolve()
    if not qa_dir.is_dir(): issues.append({"severity": "blocker", "code": "qa_dir_missing", "path": str(qa_dir)})
    for name, path in (("render_report", args.render_report), ("finalizer_receipt", args.finalizer_receipt), ("authoring_contract", args.authoring_contract)):
        value = load(path)
        if not isinstance(value, dict): issues.append({"severity": "blocker", "code": f"{name}_unreadable", "path": path})
    if not args.repo_sha or len(args.repo_sha) != 40: issues.append({"severity": "blocker", "code": "repo_sha_invalid", "observed": args.repo_sha})
    if args.render_tool in {"", "unspecified", "unknown"}: issues.append({"severity": "blocker", "code": "render_tool_unspecified"})
    result = {"schema": "ai-ppt-plus/source-manifest/v2", "valid": not issues, "status": "passed" if not issues else "blocked",
              "generated_at": datetime.now(timezone.utc).isoformat(), "repository_sha": args.repo_sha,
              "inputs": inputs, "fonts": fonts, "independent_image_assets": assets,
              "build_script": record(args.build_script), "final_pptx": record(args.pptx),
              "qa_dir": str(qa_dir), "render_tool": args.render_tool,
              "render_report": {"path": str(Path(args.render_report).resolve()), "sha256": record(args.render_report)["sha256"]},
              "finalizer_receipt": {"path": str(Path(args.finalizer_receipt).resolve()), "sha256": record(args.finalizer_receipt)["sha256"]},
              "authoring_contract": {"path": str(Path(args.authoring_contract).resolve()), "sha256": record(args.authoring_contract)["sha256"]},
              "issues": issues}
    atomic_write_json(Path(args.output).resolve(), result); print(json.dumps(result, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__": raise SystemExit(main())
