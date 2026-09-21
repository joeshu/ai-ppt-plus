#!/usr/bin/env python3
"""Fail fast on finalization prerequisites before visual repair rounds begin."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/finalization-preflight/v1"


def _inside(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _runtime_path(explicit: str | None, primary: str, fallback: str) -> Path | None:
    raw = explicit or os.environ.get(primary) or os.environ.get(fallback)
    return Path(raw).expanduser().resolve() if raw else None


def validate(
    *,
    workspace: Path,
    candidate: Path,
    final: Path,
    receipt: Path,
    node: Path | None,
    node_modules: Path | None,
    font_dir: Path | None,
) -> dict:
    issues: list[dict] = []
    workspace = workspace.resolve()
    candidate = candidate.resolve()
    final = final.resolve()
    receipt = receipt.resolve()

    if not workspace.is_dir():
        issues.append({"severity": "blocker", "code": "workspace_missing", "path": str(workspace)})
    if not candidate.is_file():
        issues.append({"severity": "blocker", "code": "candidate_missing", "path": str(candidate)})
    if candidate == final:
        issues.append({"severity": "blocker", "code": "candidate_final_path_collision", "path": str(final)})
    if not _inside(workspace, final):
        issues.append({"severity": "blocker", "code": "final_outside_workspace", "path": str(final)})
    if final.exists():
        issues.append({"severity": "blocker", "code": "final_output_already_exists", "path": str(final), "recovery": "choose a new final output path"})

    final_parent = final.parent
    receipt_parent = receipt.parent
    if not final_parent.is_dir():
        issues.append({"severity": "blocker", "code": "final_parent_missing", "path": str(final_parent), "recovery": f"mkdir -p {final_parent}"})
    if not receipt_parent.is_dir():
        issues.append({"severity": "blocker", "code": "receipt_parent_missing", "path": str(receipt_parent), "recovery": f"mkdir -p {receipt_parent}"})
    elif not _inside(workspace, receipt):
        issues.append({"severity": "blocker", "code": "receipt_outside_workspace", "path": str(receipt)})
    elif receipt_parent == final_parent or _inside(final_parent, receipt_parent):
        issues.append({"severity": "blocker", "code": "receipt_inside_final_output", "path": str(receipt)})

    node_ok = bool(node and node.is_file() and os.access(node, os.X_OK))
    if not node_ok:
        issues.append({"severity": "blocker", "code": "runtime_node_unavailable", "path": str(node) if node else None})
    package = node_modules / "@oai" / "artifact-tool" / "package.json" if node_modules else None
    if not package or not package.is_file():
        issues.append({"severity": "blocker", "code": "artifact_tool_package_missing", "path": str(package) if package else None})

    font_files = []
    if font_dir and font_dir.is_dir():
        font_files = sorted(
            str(path.resolve())
            for path in font_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".ttf", ".otf", ".ttc"}
        )
    if not font_files:
        issues.append({"severity": "blocker", "code": "font_directory_empty", "path": str(font_dir) if font_dir else None})

    for command in ("soffice", "pdftoppm"):
        if not shutil.which(command):
            issues.append({"severity": "blocker", "code": "renderer_command_missing", "command": command})

    return {
        "schema": SCHEMA,
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "workspace": str(workspace),
        "candidate": str(candidate),
        "final": str(final),
        "receipt": str(receipt),
        "runtime_env": {
            "RUNTIME_NODE": str(node) if node else None,
            "RUNTIME_NODE_MODULES": str(node_modules) if node_modules else None,
        },
        "font_files": font_files,
        "visual_renderer": "libreoffice+poppler",
        "artifact_tool_preview_policy": "structural_diagnostic_only",
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--final", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--node")
    parser.add_argument("--node-modules")
    parser.add_argument("--font-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    result = validate(
        workspace=args.workspace,
        candidate=args.candidate,
        final=args.final,
        receipt=args.receipt,
        node=_runtime_path(args.node, "RUNTIME_NODE", "CODEX_PRIMARY_RUNTIME_NODE"),
        node_modules=_runtime_path(args.node_modules, "RUNTIME_NODE_MODULES", "CODEX_PRIMARY_RUNTIME_NODE_MODULES"),
        font_dir=args.font_dir.resolve(),
    )
    atomic_write_json(args.report.resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
