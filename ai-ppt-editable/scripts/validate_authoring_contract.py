#!/usr/bin/env python3
"""Gate strict editable authoring to JavaScript ESM and artifact-tool."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from atomic_output import atomic_write_json


SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: str | None):
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--builder", required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output", required=True, help="final PPTX")
    parser.add_argument("--report", required=True)
    parser.add_argument("--repo-sha", required=True)
    parser.add_argument("--qa-dir", required=True)
    parser.add_argument("--render-report")
    parser.add_argument("--finalizer-receipt")
    parser.add_argument("--font-report")
    parser.add_argument("--marker-count", type=int, default=1)
    parser.add_argument("--fallback-used", action="store_true")
    parser.add_argument("--image-exception", action="append", default=[], help="role:path or role=path")
    args = parser.parse_args()

    builder = Path(args.builder).resolve()
    output = Path(args.output).resolve()
    qa_dir = Path(args.qa_dir).resolve()
    issues: list[dict] = []
    if not SHA_RE.fullmatch(args.repo_sha):
        issues.append({"severity": "blocker", "code": "repo_sha_invalid", "observed": args.repo_sha})
    if not builder.is_file():
        issues.append({"severity": "blocker", "code": "builder_missing", "path": str(builder)})
        source = ""
        adapter = ""
        adapter_path = None
    else:
        source = builder.read_text(encoding="utf-8")
        adapter_path = None
        adapter = ""
        # Builders may use the repository's ESM runtime adapter to discover
        # the primary runtime node_modules directory.  Follow only an
        # explicit same-directory relative import so this gate remains
        # fail-closed and cannot be satisfied by an unrelated package string.
        if "@oai/artifact-tool" not in source:
            match = re.search(r"from\s+[\"'](\.?\.?/[^\"']+\.mjs)[\"']", source)
            if match:
                candidate = (builder.parent / match.group(1)).resolve()
                if candidate.is_file():
                    adapter_path = candidate
                    adapter = candidate.read_text(encoding="utf-8")
        if builder.suffix != ".mjs":
            issues.append({"severity": "blocker", "code": "builder_not_esm_file", "path": str(builder)})
        artifact_source = source if "@oai/artifact-tool" in source else adapter
        if "@oai/artifact-tool" not in artifact_source:
            issues.append({"severity": "blocker", "code": "artifact_tool_import_missing"})
        if "PresentationFile.exportPptx" not in source and "exportPptx" not in source:
            issues.append({"severity": "blocker", "code": "artifact_tool_export_missing"})
        forbidden_source = f"{source}\n{adapter}"
        forbidden = [token for token in ("python-pptx", "from pptx", "import pptx", "pptxgenjs") if token in forbidden_source]
        if forbidden:
            issues.append({"severity": "blocker", "code": "forbidden_authoring_backend", "tokens": forbidden})
    if not output.is_file():
        issues.append({"severity": "blocker", "code": "final_output_missing", "path": str(output)})
    if not qa_dir.is_dir():
        issues.append({"severity": "blocker", "code": "qa_dir_missing", "path": str(qa_dir)})
    if args.marker_count != 1:
        issues.append({"severity": "blocker", "code": "artifact_operation_marker_count_invalid", "observed": args.marker_count, "expected": 1})
    if args.fallback_used:
        issues.append({"severity": "blocker", "code": "unapproved_fallback_used"})
    render = load(args.render_report)
    if args.render_report and not isinstance(render, dict):
        issues.append({"severity": "blocker", "code": "render_report_unreadable", "path": args.render_report})
    font = load(args.font_report)
    if args.font_report and not isinstance(font, dict):
        issues.append({"severity": "blocker", "code": "font_report_unreadable", "path": args.font_report})
    receipt = load(args.finalizer_receipt)
    if args.finalizer_receipt and not isinstance(receipt, dict):
        issues.append({"severity": "blocker", "code": "finalizer_receipt_unreadable", "path": args.finalizer_receipt})
    output_sha = digest(output)
    if isinstance(receipt, dict) and output_sha:
        reported_sha = receipt.get("finalSha256")
        if reported_sha != output_sha:
            issues.append({"severity": "blocker", "code": "finalizer_output_hash_mismatch", "message": "finalizer receipt does not identify the exact requested output", "reported": reported_sha, "observed": output_sha})
        import_sha = ((receipt.get("firstPartyImport") or {}).get("sha256"))
        if import_sha != output_sha:
            issues.append({"severity": "blocker", "code": "finalizer_import_hash_mismatch", "message": "first-party import evidence does not identify the exact requested output", "reported": import_sha, "observed": output_sha})
    exceptions = []
    for item in args.image_exception:
        role, sep, value = item.partition(":") if ":" in item else item.partition("=")
        if not sep or not role or not value:
            issues.append({"severity": "blocker", "code": "image_exception_invalid", "value": item})
            continue
        path = Path(value).resolve()
        if not path.is_file():
            issues.append({"severity": "blocker", "code": "image_exception_missing", "role": role, "path": str(path)})
        exceptions.append({"role": role, "path": str(path), "sha256": digest(path)})
    result = {
        "schema": "ai-ppt-plus/authoring-contract/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "backend": "@oai/artifact-tool",
        "language": "javascript",
        "module_format": "ESM",
        "builder": {"path": str(builder), "sha256": digest(builder)},
        "artifact_tool_resolution": {
            "source": "builder" if "@oai/artifact-tool" in source else "same-directory-runtime-adapter" if adapter_path else None,
            "adapter": {"path": str(adapter_path), "sha256": digest(adapter_path)} if adapter_path else None,
        },
        "output": {"path": str(output), "sha256": output_sha},
        "repo_sha": args.repo_sha,
        "qa_dir": str(qa_dir),
        "artifact_operation_marker": {"count": args.marker_count, "status": "exactly_once" if args.marker_count == 1 else "invalid"},
        "fallback_used": args.fallback_used,
        "image_exceptions": exceptions,
        "render_evidence": render,
        "font_evidence": font,
        "finalizer_evidence": receipt,
        "issues": issues,
    }
    atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
