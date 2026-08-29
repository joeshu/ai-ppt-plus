#!/usr/bin/env python3
"""Create, verify, and materialize immutable project revision snapshots.

No operation overwrites the source project. `prepare` creates a new snapshot,
`verify` checks its hashes, and `materialize` copies it to a new work directory
for recovery or rollback work.

Usage:
  revision_guard.py freeze --root ROOT --output-dir BASELINE --revision R13 \
      --artifact deck/final.pptx=source/deck.pptx
  revision_guard.py prepare PROJECT_DIR --deck DECK --label R4
  revision_guard.py verify SNAPSHOT_DIR
  revision_guard.py materialize SNAPSHOT_DIR --output-dir NEW_DIR

`freeze` accepts repeated `--artifact ARCHIVE_PATH=SOURCE_PATH` arguments and
creates `baseline-manifest.json` plus `SHA256SUMS`. Existing targets are never
overwritten.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from atomic_output import atomic_copy, atomic_write_json, atomic_write_text


FILES = (
    "handoff.json", "deck-brief.md", "source-inventory.json", "design-system.yaml",
    "material-inventory.json", "route-decision.json", "visual-intermediate-manifest.json",
    "layout.json", "slide-manifest.json", "slide-object-manifest.json",
    "asset-manifest.json", "panel-asset-manifest.json", "icon-asset-manifest.json",
    "imagegen-assets-manifest.json", "gradient-asset-manifest.json",
    "validation-report.json", "report-index.json", "project-report.json",
    "issue-log.json", "delivery-report.md",
)


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _safe_relative_path(value: str, *, allow_metadata: bool = False) -> Path:
    """Return a safe archive-relative path or raise ValueError."""
    normalized = str(value).strip().replace("\\", "/")
    path = Path(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe archive path: {value!r}")
    reserved = {".", "snapshot.json"}
    if not allow_metadata:
        reserved.update({"baseline-manifest.json", "SHA256SUMS"})
    if normalized in reserved:
        raise ValueError(f"reserved archive path: {value!r}")
    return path


def _parse_artifact_spec(spec: str) -> tuple[Path, str]:
    """Parse ``ARCHIVE_PATH=SOURCE_PATH`` without guessing missing paths."""
    if "=" not in spec:
        raise ValueError("artifact must use ARCHIVE_PATH=SOURCE_PATH")
    destination_text, source_text = spec.split("=", 1)
    destination = _safe_relative_path(destination_text)
    source_text = source_text.strip()
    if not source_text:
        raise ValueError(f"artifact source is empty: {spec!r}")
    return destination, source_text


def _source_reference(source: Path, root: Path) -> dict:
    """Describe the source without making the archive depend on host paths."""
    try:
        relative = source.relative_to(root)
    except ValueError:
        return {"scope": "external", "path": source.name}
    return {"scope": "root", "path": relative.as_posix()}


def _write_checksums(directory: Path, records: list[dict]) -> None:
    """Write a standard checksum list for copied artifacts and its manifest."""
    entries = [(record["path"], record["sha256"]) for record in records]
    manifest = directory / "baseline-manifest.json"
    entries.append((manifest.name, digest(manifest)))
    content = "".join(f"{sha}  {path}\n" for path, sha in sorted(entries))
    atomic_write_text(directory / "SHA256SUMS", content)


def _read_checksums(path: Path) -> dict[str, str]:
    checksums = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            sha, relative = line.split("  ", 1)
        except ValueError as exc:
            raise ValueError(f"invalid checksum line {line_no}") from exc
        if len(sha) != 64 or any(char not in "0123456789abcdef" for char in sha.lower()):
            raise ValueError(f"invalid checksum on line {line_no}")
        safe = _safe_relative_path(relative, allow_metadata=True)
        if safe.as_posix() in checksums:
            raise ValueError(f"duplicate checksum path: {safe.as_posix()}")
        checksums[safe.as_posix()] = sha.lower()
    return checksums


def freeze_baseline(root: Path, output: Path, revision: str, source_case: str,
                    artifacts: list[str], excluded_revisions: list[str],
                    known_open_issues: list[str]) -> int:
    """Create a self-contained, no-overwrite baseline archive.

    ``artifacts`` uses ``archive/path=source/path``. The source side is
    resolved relative to ``root`` unless it is absolute. The archive stores
    only relative source references, copied bytes, and SHA-256 evidence.
    """
    if output.exists():
        print(json.dumps({"valid": False, "code": "baseline_exists", "path": str(output)}, ensure_ascii=False))
        return 2
    root = root.resolve()
    output = output.resolve()
    try:
        specs = [_parse_artifact_spec(item) for item in artifacts]
    except ValueError as exc:
        print(json.dumps({"valid": False, "code": "invalid_artifact_spec", "message": str(exc)}, ensure_ascii=False))
        return 2
    destinations = [destination.as_posix() for destination, _ in specs]
    if len(set(destinations)) != len(destinations):
        print(json.dumps({"valid": False, "code": "duplicate_artifact_destination"}, ensure_ascii=False))
        return 2

    sources = []
    missing = []
    for destination, source_text in specs:
        source = Path(source_text).expanduser()
        if not source.is_absolute():
            source = root / source
        source = source.resolve()
        if not source.is_file():
            missing.append({"path": destination.as_posix(), "source": str(source)})
        sources.append((destination, source))
    if missing:
        print(json.dumps({"valid": False, "code": "artifact_source_missing", "missing": missing}, ensure_ascii=False))
        return 2

    output.mkdir(parents=True)
    records = []
    try:
        for destination, source in sources:
            target = output / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_copy(source, target)
            records.append({
                "path": destination.as_posix(),
                "source": _source_reference(source, root),
                "sha256": digest(target),
                "size": target.stat().st_size,
            })
        records.sort(key=lambda item: item["path"])
        manifest = {
            "schema": "ai-ppt-plus/baseline/v1",
            "revision": revision,
            "source_case": source_case,
            "status": "frozen",
            "immutable": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "artifact_count": len(records),
            "artifacts": records,
            "excluded_revisions": list(excluded_revisions),
            "known_open_issues": list(known_open_issues),
            "checksum_file": "SHA256SUMS",
            "verification": "python scripts/revision_guard.py verify <baseline-dir>",
        }
        atomic_write_json(output / "baseline-manifest.json", manifest)
        _write_checksums(output, records)
    except Exception as exc:
        print(json.dumps({"valid": False, "code": "baseline_write_failed", "message": f"{type(exc).__name__}: {exc}", "path": str(output)}, ensure_ascii=False))
        return 2

    print(json.dumps({
        "valid": True,
        "operation": "freeze",
        "baseline": str(output),
        "revision": revision,
        "artifacts": len(records),
        "excluded_revisions": list(excluded_revisions),
    }, ensure_ascii=False))
    return 0


def verify_baseline(directory: Path) -> int:
    """Verify baseline bytes, declared sizes, manifest and checksum list."""
    metadata_path = directory / "baseline-manifest.json"
    checksum_path = directory / "SHA256SUMS"
    issues = []
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"valid": False, "code": "baseline_manifest_unreadable", "message": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 2
    if metadata.get("schema") != "ai-ppt-plus/baseline/v1":
        issues.append({"code": "baseline_schema_invalid"})
    if metadata.get("status") != "frozen" or metadata.get("immutable") is not True:
        issues.append({"code": "baseline_not_frozen"})
    records = metadata.get("artifacts")
    if not isinstance(records, list) or not records:
        issues.append({"code": "baseline_artifacts_missing"})
        records = []
    expected_paths = set()
    for record in records:
        if not isinstance(record, dict):
            issues.append({"code": "baseline_artifact_record_invalid"})
            continue
        try:
            relative = _safe_relative_path(str(record.get("path", ""))).as_posix()
        except ValueError as exc:
            issues.append({"code": "baseline_artifact_path_invalid", "message": str(exc)})
            continue
        if relative in expected_paths:
            issues.append({"code": "baseline_artifact_duplicate", "path": relative})
        expected_paths.add(relative)
        path = directory / relative
        if not path.is_file():
            issues.append({"code": "baseline_artifact_missing", "path": relative})
            continue
        observed_sha = digest(path)
        if observed_sha != record.get("sha256"):
            issues.append({"code": "baseline_artifact_hash_mismatch", "path": relative, "expected": record.get("sha256"), "observed": observed_sha})
        if path.stat().st_size != record.get("size"):
            issues.append({"code": "baseline_artifact_size_mismatch", "path": relative})
    if metadata.get("artifact_count") != len(records):
        issues.append({"code": "baseline_artifact_count_mismatch"})

    checksum_entries = {}
    if not checksum_path.is_file():
        issues.append({"code": "baseline_checksums_missing"})
    else:
        try:
            checksum_entries = _read_checksums(checksum_path)
        except (OSError, ValueError) as exc:
            issues.append({"code": "baseline_checksums_invalid", "message": str(exc)})
    expected_checksum_paths = expected_paths | {"baseline-manifest.json"}
    if checksum_entries:
        if set(checksum_entries) != expected_checksum_paths:
            issues.append({"code": "baseline_checksum_scope_mismatch", "expected": sorted(expected_checksum_paths), "observed": sorted(checksum_entries)})
        for relative in expected_checksum_paths:
            path = directory / relative
            if path.is_file() and checksum_entries.get(relative) != digest(path):
                issues.append({"code": "baseline_checksum_mismatch", "path": relative})
    result = {"valid": not issues, "operation": "verify-baseline", "baseline": str(directory.resolve()), "revision": metadata.get("revision"), "artifacts": len(records), "issues": issues}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


def snapshot_files(project: Path, deck: Path):
    sources = [(deck, deck.name)]
    for name in FILES:
        path = project / name
        if path.is_file():
            sources.append((path, name))
    return sources


def prepare(project: Path, deck: Path, label: str) -> int:
    root = project / "revisions"
    target = root / f"{label}-baseline"
    if target.exists():
        # A DAG retry can legitimately reach the revision-preparation step
        # after a previous attempt already created the immutable snapshot.
        # Reuse it only when every current source byte still matches the
        # recorded snapshot; never overwrite or silently reuse a stale one.
        metadata_path = target / "snapshot.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            records = metadata.get("files") if isinstance(metadata, dict) else None
            current = snapshot_files(project, deck)
            by_name = {str(record.get("name")): record for record in records or [] if isinstance(record, dict)}
            reusable = (
                metadata.get("schema") == "ai-ppt-plus/revision-snapshot/v1"
                and metadata.get("label") == label
                and len(by_name) == len(current)
                and all(
                    name in by_name
                    and Path(record["snapshot"]).is_file()
                    and digest(source) == record.get("sha256") == digest(Path(record["snapshot"]))
                    for source, name in current
                    for record in [by_name.get(name, {})]
                )
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            reusable = False
        if reusable:
            print(json.dumps({"valid": True, "operation": "prepare", "reused": True, "snapshot": str(target.resolve()), "files": len(current)}, ensure_ascii=False))
            return 0
        print(json.dumps({"valid": False, "code": "snapshot_exists", "path": str(target), "message": "existing snapshot is immutable and no longer matches current sources; use a new revision label"}, ensure_ascii=False))
        return 2
    target.mkdir(parents=True)
    records = []
    for source, name in snapshot_files(project, deck):
        destination = target / name
        atomic_copy(source, destination)
        records.append({"name": name, "source": str(source.resolve()), "snapshot": str(destination.resolve()), "sha256": digest(destination), "size": destination.stat().st_size})
    metadata = {"schema": "ai-ppt-plus/revision-snapshot/v1", "label": label, "created_at": datetime.now(timezone.utc).isoformat(), "project": str(project), "files": records, "immutable_source": True}
    atomic_write_json(target / "snapshot.json", metadata)
    print(json.dumps({"valid": True, "operation": "prepare", "snapshot": str(target.resolve()), "files": len(records)}, ensure_ascii=False))
    return 0


def verify(snapshot: Path) -> int:
    if (snapshot / "baseline-manifest.json").is_file():
        return verify_baseline(snapshot)
    metadata_path = snapshot / "snapshot.json"
    if not metadata_path.is_file():
        print(json.dumps({"valid": False, "code": "snapshot_metadata_missing"}, ensure_ascii=False))
        return 2
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    issues = []
    for record in metadata.get("files", []):
        path = Path(record["snapshot"])
        if not path.is_file():
            issues.append({"code": "snapshot_file_missing", "name": record.get("name")})
        elif digest(path) != record.get("sha256"):
            issues.append({"code": "snapshot_hash_mismatch", "name": record.get("name")})
    result = {"valid": not issues, "operation": "verify", "snapshot": str(snapshot.resolve()), "issues": issues}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


def materialize(snapshot: Path, output: Path) -> int:
    if output.exists():
        print(json.dumps({"valid": False, "code": "output_exists", "path": str(output)}, ensure_ascii=False))
        return 2
    check = verify(snapshot)
    if check:
        return check
    metadata = json.loads((snapshot / "snapshot.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    records = []
    for record in metadata["files"]:
        source = Path(record["snapshot"])
        destination = output / record["name"]
        atomic_copy(source, destination)
        records.append({"name": record["name"], "path": str(destination.resolve()), "sha256": digest(destination)})
    handoff = {"schema": "ai-ppt-plus/rollback-materialization/v1", "source_snapshot": str(snapshot.resolve()), "created_at": datetime.now(timezone.utc).isoformat(), "files": records, "requires_review": True}
    atomic_write_json(output / "rollback-materialization.json", handoff)
    print(json.dumps({"valid": True, "operation": "materialize", "output": str(output.resolve()), "files": len(records), "requires_review": True}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    freeze_parser = sub.add_parser("freeze", help="freeze a self-contained multi-artifact baseline")
    freeze_parser.add_argument("--root", default=".", help="root for relative source paths")
    freeze_parser.add_argument("--output-dir", required=True)
    freeze_parser.add_argument("--revision", required=True)
    freeze_parser.add_argument("--source-case", default="")
    freeze_parser.add_argument("--artifact", action="append", required=True, help="ARCHIVE_PATH=SOURCE_PATH; may be repeated")
    freeze_parser.add_argument("--exclude-revision", action="append", default=[])
    freeze_parser.add_argument("--known-open-issue", action="append", default=[])
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("project_dir")
    prepare_parser.add_argument("--deck", required=True)
    prepare_parser.add_argument("--label", required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("snapshot_dir")
    materialize_parser = sub.add_parser("materialize")
    materialize_parser.add_argument("snapshot_dir")
    materialize_parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    if args.operation == "freeze":
        return freeze_baseline(
            Path(args.root),
            Path(args.output_dir),
            args.revision,
            args.source_case,
            args.artifact,
            args.exclude_revision,
            args.known_open_issue,
        )
    if args.operation == "prepare":
        return prepare(Path(args.project_dir).resolve(), Path(args.deck).resolve(), args.label)
    if args.operation == "verify":
        return verify(Path(args.snapshot_dir).resolve())
    return materialize(Path(args.snapshot_dir).resolve(), Path(args.output_dir).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
