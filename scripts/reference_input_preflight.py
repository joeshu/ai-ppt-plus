#!/usr/bin/env python3
"""Resolve image inputs and prove the exact reference roster before authoring.

The resolver is deliberately bounded: it checks the caller's paths, the current
workspace and its ``upload/`` directory, plus deterministic upload suffixes.
It never downloads, rewrites, or silently picks between different images.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from PIL import Image

from atomic_output import atomic_write_json


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
SUFFIX_RE = re.compile(r"^(?P<stem>.*?)(?:\s*\((?P<paren>\d+)\)|[-_](?P<number>\d+))$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def variants(path: Path) -> list[str]:
    stem, suffix = path.stem, path.suffix
    values = [path.name]
    match = SUFFIX_RE.match(stem)
    base = match.group("stem") if match else stem
    for token in (" (1)", "(1)", "-1", "_1", " (2)", "(2)", "-2", "_2"):
        values.append(f"{base}{token}{suffix}")
    return list(dict.fromkeys(values))


def bounded_roots(requested: Path, search_roots: list[Path]) -> list[Path]:
    cwd = Path.cwd().resolve()
    roots = [cwd, cwd / "upload", requested.parent.resolve(), requested.parent.resolve() / "upload"]
    roots.extend(Path(value).resolve() for value in search_roots)
    result = []
    for root in roots:
        if root.is_dir() and root not in result:
            result.append(root)
    return result


def inspect(path: Path) -> dict:
    resolved = path.resolve()
    record = {"path": str(resolved), "filename": resolved.name, "sha256": sha256(resolved)}
    try:
        with Image.open(resolved) as image:
            width, height = image.size
            record.update({"width": width, "height": height, "ratio": round(width / height, 8), "format": image.format})
    except Exception as exc:
        record.update({"width": None, "height": None, "ratio": None, "format": None,
                       "decode_error": f"{type(exc).__name__}: {exc}"})
    return record


def resolve(requested: str, search_roots: list[Path]) -> tuple[dict | None, list[dict]]:
    asked = Path(requested).expanduser()
    candidates: list[Path] = []
    if asked.is_file():
        candidates.append(asked.resolve())
    else:
        names = variants(asked)
        for root in bounded_roots(asked, search_roots):
            for name in names:
                path = root / name
                if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                    candidates.append(path.resolve())
            # A controlled basename search handles platform upload renames that
            # retain a longer numeric suffix, without scanning the repository.
            for path in sorted(root.glob(f"{asked.stem}*{asked.suffix}")):
                if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                    candidates.append(path.resolve())
    candidates = list(dict.fromkeys(candidates))
    records = [inspect(path) for path in candidates]
    usable = [record for record in records if not record.get("decode_error")]
    if not usable:
        return None, records
    hashes = {record["sha256"] for record in usable}
    if len(hashes) > 1:
        return None, records
    # Prefer an exact requested basename, then a deterministic shortest path.
    usable.sort(key=lambda record: (record["filename"] != asked.name, len(record["path"]), record["path"]))
    return usable[0], records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, help="reference image path; repeat per page")
    parser.add_argument("--search-root", action="append", default=[], help="additional bounded search directory")
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--expected-ratio", type=float)
    parser.add_argument("--ratio-tolerance", type=float, default=0.01)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output", "-o", required=True)
    args = parser.parse_args()

    issues: list[dict] = []
    resolved: list[dict] = []
    candidate_evidence: list[dict] = []
    for index, value in enumerate(args.input, start=1):
        record, candidates = resolve(value, [Path(item) for item in args.search_root])
        candidate_evidence.append({"requested": value, "candidates": candidates})
        if record is None:
            code = "input_not_found" if not candidates else "ambiguous_input_hashes"
            issues.append({"severity": "blocker", "code": code, "page": index, "requested": value,
                           "candidates": candidates})
            continue
        record = {"page": index, "requested": value, **record}
        resolved.append(record)
        if record.get("decode_error"):
            issues.append({"severity": "blocker", "code": "image_decode_failed", "page": index,
                           "error": record["decode_error"]})
        if args.expected_ratio and record.get("ratio") is not None:
            if abs(record["ratio"] - args.expected_ratio) > args.ratio_tolerance:
                issues.append({"severity": "blocker", "code": "aspect_ratio_mismatch", "page": index,
                               "observed": record["ratio"], "expected": args.expected_ratio,
                               "tolerance": args.ratio_tolerance})
    if args.expected_count is not None and len(args.input) != args.expected_count:
        issues.append({"severity": "blocker", "code": "page_count_mismatch", "observed": len(args.input),
                       "expected": args.expected_count})
    seen: dict[str, int] = {}
    for record in resolved:
        previous = seen.get(record["sha256"])
        if previous is not None and previous != record["page"]:
            issues.append({"severity": "blocker", "code": "duplicate_reference_image", "pages": [previous, record["page"]],
                           "sha256": record["sha256"]})
        seen[record["sha256"]] = record["page"]
    if len(resolved) != len(args.input):
        issues.append({"severity": "blocker", "code": "resolved_page_count_mismatch",
                       "observed": len(resolved), "expected": len(args.input)})
    result = {
        "schema": "ai-ppt-plus/reference-input-preflight/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "strict": args.strict,
        "expected_count": args.expected_count,
        "expected_ratio": args.expected_ratio,
        "inputs": resolved,
        "candidate_evidence": candidate_evidence,
        "issues": issues,
        "rule": "Missing old paths are resolved only from bounded workspace/upload/name-variant search; different candidate hashes block instead of being guessed.",
    }
    atomic_write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
