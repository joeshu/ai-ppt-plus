#!/usr/bin/env python3
"""Build a release-facing reconstruction capability status without conflating evidence classes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA = "ai-ppt-plus/reconstruction-capability-status/v1"


def load(path: str | None) -> dict:
    if not path:
        return {}
    value = Path(path)
    return json.loads(value.read_text(encoding="utf-8")) if value.is_file() else {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engineering-report")
    parser.add_argument("--four-evidence-report")
    parser.add_argument("--host-validation-report")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    engineering = load(args.engineering_report)
    evidence = load(args.four_evidence_report)
    host = load(args.host_validation_report)

    engineering_passed = bool(engineering.get("valid") or engineering.get("strict_gate", {}).get("passed"))
    visual_evidence_complete = bool(evidence.get("valid"))
    visual_human_confirmed = evidence.get("human_visual_review_status") == "passed"
    host_passed = bool(host.get("valid")) and str(host.get("status") or host.get("evidence_status") or "passed") == "passed"

    release_eligible = engineering_passed and visual_evidence_complete and visual_human_confirmed and host_passed
    result = {
        "schema": SCHEMA,
        "engineering_gate": {
            "status": "passed" if engineering_passed else "blocked",
            "meaning": "deterministic structure/editability/automated QA only",
        },
        "visual_evidence": {
            "status": "confirmed" if visual_human_confirmed else "evidence-ready" if visual_evidence_complete else "incomplete",
            "meaning": "reference/render/diff/object-tree evidence; human visual confirmation is separate",
        },
        "host_validation": {
            "status": "passed" if host_passed else "pending",
            "meaning": "actual PowerPoint/WPS host opening, typography, overflow and editability evidence",
        },
        "release_eligible": release_eligible,
        "capability_statement": (
            "validated editable high-fidelity reconstruction delivery"
            if release_eligible else
            "engineering validation complete; visual/host evidence remains separate until explicitly confirmed"
            if engineering_passed else
            "engineering reconstruction validation incomplete"
        ),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
