#!/usr/bin/env python3
"""Regression coverage for recovery and human-approval evidence integrity."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, script, *args], cwd=ROOT, capture_output=True, text=True, check=False)


def worker(name: str, revision: str) -> dict:
    return {
        "protocol": "ai-ppt-plus/worker-handoff/v1",
        "skill": name,
        "skill_revision": revision,
        "status": "passed",
        "input_hashes": [],
        "output_artifacts": [],
        "manifest_paths": [],
        "qa_results": [],
        "known_issues": [],
        "next_action": "return to root",
    }


def main() -> int:
    revision = json.loads((ROOT / "assets/skill-package.json").read_text(encoding="utf-8"))["package_revision"]
    with tempfile.TemporaryDirectory(prefix="p0-integrity-") as temp:
        root = Path(temp)
        deck = root / "deck.pptx"
        deck.write_bytes(b"exact-deck-bytes")
        evidence = root / "evidence.json"
        write_json(evidence, {"valid": True})
        handoff = root / "handoff.json"
        write_json(handoff, {
            "schema": "ai-ppt-plus/handoff/v2",
            "project_id": "integrity",
            "run_id": "run-1",
            "revision": "R1",
            "package_revision": revision,
            "route": "reference-reconstruction",
            "current_stage": "validated",
            "gate_status": "passed",
            "approved_artifacts": {"pptx": deck.name, "pptx_sha256": digest(deck)},
            "artifacts": {"evidence": {"path": evidence.name, "required": True, "exists": True, "sha256": digest(evidence)}},
            "completed_slides": [1],
            "active_batch": [],
            "remaining_slides": [],
            "open_blockers": [],
            "repair_round": 0,
            "latest_checks": [],
            "backend": "pptxgenjs",
            "next_action": "human closeout",
            "updated_at": "2026-08-31T00:00:00Z",
            "handoff_protocol": "ai-ppt-plus/worker-handoff/v1",
            "worker_handoffs": {"visual": worker("visual", revision), "editable": worker("editable", revision)},
            "cross_artifact": {"expected_pages": 1, "page_coverage": {"completed": [1], "remaining": []}},
        })
        checked = run("scripts/validate_handoff.py", str(handoff), "--require-worker-protocol", "--expected-package-revision", revision)
        assert checked.returncode == 0, checked.stdout + checked.stderr

        mismatch = run("scripts/validate_handoff.py", str(handoff), "--require-worker-protocol", "--expected-package-revision", "stale-revision")
        assert mismatch.returncode == 2
        assert "package_revision_mismatch" in mismatch.stdout and "worker_revision_mismatch" in mismatch.stdout

        signoff = root / "human-signoff.json"
        write_json(signoff, {
            "narrative": True, "facts": True, "visual": True, "fidelity": True, "brand": True,
            "reviewer": "owner", "confirmed_at": "2026-08-31T00:00:00Z", "deck_sha256": digest(deck),
        })
        signoff_report = root / "signoff-validation.json"
        approved = run("scripts/validate_signoff.py", str(signoff), "--deck", str(deck), "--strict-evidence", "--report", str(signoff_report))
        assert approved.returncode == 0, approved.stdout + approved.stderr
        assert json.loads(signoff_report.read_text(encoding="utf-8"))["deck_sha256"] == digest(deck)

        deck.write_bytes(b"changed-after-approval")
        stale = run("scripts/validate_signoff.py", str(signoff), "--deck", str(deck), "--strict-evidence")
        assert stale.returncode == 2 and "signoff_deck_hash_mismatch" in stale.stdout

        release_deck = root / "release.pptx"
        with zipfile.ZipFile(release_deck, "w") as package:
            package.writestr("[Content_Types].xml", "<Types/>")
        release_hash = digest(release_deck)
        inspection = root / "inspection.json"
        render = root / "render.json"
        manifest = root / "slide-manifest.json"
        dual = root / "dual.json"
        decisions = root / "release-signoff.json"
        write_json(inspection, {"ok": True, "deck_sha256": release_hash, "slide_count": 1})
        write_json(render, {"ok": True, "deck_sha256": release_hash, "pages": [{"slide": 1}]})
        write_json(manifest, {"slides": [{"slide_no": 1, "formal_content_source": "approved outline", "objects": []}]})
        write_json(decisions, {"narrative": True, "facts": True, "visual": True, "fidelity": True, "brand": True})
        write_json(dual, {"valid": True, "status": "passed", "deck_sha256": "0" * 64, "pixel_comparison": {"valid": True}, "object_comparison": {"valid": True}, "issues": []})
        delivery_args = (
            str(release_deck), "--inspection", str(inspection), "--render-report", str(render),
            "--manifest", str(manifest), "--human-signoff", str(decisions),
            "--dual-comparison", str(dual), "--require-dual-comparison",
            "--quality-score", "100", "--output", str(root / "delivery.json"),
        )
        stale_delivery = run("scripts/delivery_check.py", *delivery_args)
        assert stale_delivery.returncode == 2 and "stale_dual_comparison" in stale_delivery.stdout
        dual_data = json.loads(dual.read_text(encoding="utf-8")); dual_data["deck_sha256"] = release_hash; write_json(dual, dual_data)
        current_delivery = run("scripts/delivery_check.py", *delivery_args)
        assert current_delivery.returncode == 0, current_delivery.stdout + current_delivery.stderr

    print("P0 recovery and sign-off integrity: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
