#!/usr/bin/env python3
"""Create, verify, and materialize immutable project revision snapshots.

No operation overwrites the source project. `prepare` creates a new snapshot,
`verify` checks its hashes, and `materialize` copies it to a new work directory
for recovery or rollback work.

Usage:
  revision_guard.py prepare PROJECT_DIR --deck DECK --label R4
  revision_guard.py verify SNAPSHOT_DIR
  revision_guard.py materialize SNAPSHOT_DIR --output-dir NEW_DIR
"""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


FILES = (
    "handoff.json", "deck-brief.md", "source-inventory.json", "design-system.yaml",
    "slide-manifest.json", "asset-manifest.json", "validation-report.json",
    "issue-log.json", "delivery-report.md",
)


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


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
        print(json.dumps({"valid": False, "code": "snapshot_exists", "path": str(target)}, ensure_ascii=False))
        return 2
    target.mkdir(parents=True)
    records = []
    for source, name in snapshot_files(project, deck):
        destination = target / name
        shutil.copy2(source, destination)
        records.append({"name": name, "source": str(source.resolve()), "snapshot": str(destination.resolve()), "sha256": digest(destination), "size": destination.stat().st_size})
    metadata = {"schema": "ai-ppt-plus/revision-snapshot/v1", "label": label, "created_at": datetime.now(timezone.utc).isoformat(), "project": str(project), "files": records, "immutable_source": True}
    (target / "snapshot.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"valid": True, "operation": "prepare", "snapshot": str(target.resolve()), "files": len(records)}, ensure_ascii=False))
    return 0


def verify(snapshot: Path) -> int:
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
        shutil.copy2(source, destination)
        records.append({"name": record["name"], "path": str(destination.resolve()), "sha256": digest(destination)})
    handoff = {"schema": "ai-ppt-plus/rollback-materialization/v1", "source_snapshot": str(snapshot.resolve()), "created_at": datetime.now(timezone.utc).isoformat(), "files": records, "requires_review": True}
    (output / "rollback-materialization.json").write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"valid": True, "operation": "materialize", "output": str(output.resolve()), "files": len(records), "requires_review": True}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
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
    if args.operation == "prepare":
        return prepare(Path(args.project_dir).resolve(), Path(args.deck).resolve(), args.label)
    if args.operation == "verify":
        return verify(Path(args.snapshot_dir).resolve())
    return materialize(Path(args.snapshot_dir).resolve(), Path(args.output_dir).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
