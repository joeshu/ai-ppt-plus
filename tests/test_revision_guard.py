"""Regression tests for immutable multi-artifact baseline archives."""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "revision_guard.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="baseline-guard-") as tmp:
        root = Path(tmp)
        source = root / "source.jpeg"
        deck = root / "deck.pptx"
        preview = root / "preview.png"
        report = root / "report.json"
        source.write_bytes(b"source-bytes")
        deck.write_bytes(b"pptx-bytes")
        preview.write_bytes(b"preview-bytes")
        report.write_text(json.dumps({"valid": True}), encoding="utf-8")
        archive = root / "archive" / "R13"
        artifacts = [
            f"deck/final.pptx={deck}",
            f"source/reference.jpeg={source}",
            f"preview/slide-1.png={preview}",
            f"reports/project-report.json={report}",
        ]
        created = run(
            "freeze",
            "--root",
            str(root),
            "--output-dir",
            str(archive),
            "--revision",
            "R13",
            "--source-case",
            "fixture",
            "--exclude-revision",
            "R14",
            "--known-open-issue",
            "human-closeout-pending",
            *sum((["--artifact", item] for item in artifacts), []),
        )
        if created.returncode != 0:
            raise AssertionError(created.stdout + created.stderr)
        verified = run("verify", str(archive))
        if verified.returncode != 0:
            raise AssertionError(verified.stdout + verified.stderr)
        manifest = json.loads((archive / "baseline-manifest.json").read_text(encoding="utf-8"))
        if manifest["revision"] != "R13" or manifest["artifact_count"] != 4:
            raise AssertionError(manifest)
        for record in manifest["artifacts"]:
            copied = archive / record["path"]
            if record["sha256"] != digest(copied):
                raise AssertionError(record)
        if run("freeze", "--root", str(root), "--output-dir", str(archive), "--revision", "R13", "--artifact", f"deck/final.pptx={deck}").returncode == 0:
            raise AssertionError("existing archive must block overwrite")
        (archive / "preview/slide-1.png").write_bytes(b"changed")
        if run("verify", str(archive)).returncode == 0:
            raise AssertionError("changed artifact must fail verification")

        project = root / "project"
        project.mkdir()
        (project / "layout.json").write_text("{}", encoding="utf-8")
        snapshot_deck = project / "deck.pptx"
        snapshot_deck.write_bytes(b"snapshot-deck")
        first = run("prepare", str(project), "--deck", str(snapshot_deck), "--label", "R1")
        if first.returncode != 0:
            raise AssertionError(first.stdout + first.stderr)
        retry = run("prepare", str(project), "--deck", str(snapshot_deck), "--label", "R1")
        if retry.returncode != 0 or '"reused": true' not in retry.stdout:
            raise AssertionError("same-source retry should reuse the immutable snapshot: " + retry.stdout + retry.stderr)
        snapshot_deck.write_bytes(b"changed-deck")
        stale_retry = run("prepare", str(project), "--deck", str(snapshot_deck), "--label", "R1")
        if stale_retry.returncode == 0 or "snapshot_exists" not in stale_retry.stdout:
            raise AssertionError("stale snapshot must still block reuse")
    print("revision guard baseline: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
