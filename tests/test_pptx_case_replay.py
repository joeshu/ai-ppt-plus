#!/usr/bin/env python3
"""Run the real social-channel PPTX case, not only unit-level checks."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import is_zipfile


ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "scripts" / "replay_pptx_case.py"
PROOF = ROOT / "scripts" / "validate_distillation_improvement.py"
CASE = ROOT / "ai-ppt-editable" / "evals" / "social-channel-commission-native-01.json"


def materialize_fixture(source: Path, destination: Path, *, binary_zip: bool = False) -> Path:
    """Freeze a fixture before replay and recover a damaged checkout from Git."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    valid = is_zipfile(destination) if binary_zip else destination.stat().st_size > 0
    if not valid:
        relative = source.relative_to(ROOT).as_posix()
        recovered = subprocess.run(
            ["git", "show", f"HEAD:{relative}"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if recovered.returncode == 0 and recovered.stdout:
            destination.write_bytes(recovered.stdout)
    if binary_zip and not is_zipfile(destination):
        preview = destination.read_bytes()[:24].hex()
        raise AssertionError(
            f"fixture is not a valid PPTX ZIP: {source} "
            f"(size={destination.stat().st_size}, header={preview})"
        )
    if not destination.is_file() or destination.stat().st_size == 0:
        raise AssertionError(f"fixture is empty: {source}")
    return destination


def main() -> int:
    source = ROOT / "ai-ppt-editable" / "evals" / "fixtures" / "social-channel-commission-editable-1.pptx"
    process = ROOT / "ai-ppt-editable" / "evals" / "fixtures" / "social-channel-commission-green-screen-process.png"
    candidate = ROOT / "ai-ppt-editable" / "evals" / "fixtures" / "social-channel-commission-native-01-candidate.pptx"
    if not source.is_file() or not process.is_file() or not candidate.is_file():
        raise AssertionError("social-channel-commission-native-01 fixtures are incomplete")
    with tempfile.TemporaryDirectory(prefix="pptx-case-replay-") as temporary:
        work = Path(temporary)
        source = materialize_fixture(source, work / "source.pptx", binary_zip=True)
        process = materialize_fixture(process, work / "process.png")
        candidate = materialize_fixture(candidate, work / "candidate.pptx", binary_zip=True)
        baseline_dir = work / "baseline"
        candidate_dir = work / "candidate"
        baseline_path = baseline_dir / "baseline-evaluation.json"
        candidate_path = candidate_dir / "candidate-evaluation.json"
        base_command = [
            sys.executable, str(REPLAY), "--case-spec", str(CASE),
            "--source-pptx", str(source), "--process-image", str(process),
        ]
        baseline = subprocess.run(
            base_command + ["--phase", "baseline", "--deck", str(source), "--output-dir", str(baseline_dir), "--output", str(baseline_path)],
            capture_output=True, text=True, check=False,
        )
        assert baseline.returncode != 0, baseline.stdout + baseline.stderr
        assert baseline_path.is_file(), baseline.stdout + baseline.stderr
        baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
        assert "native-table-xml" in baseline_data["failure_codes"], baseline_data
        candidate_run = subprocess.run(
            base_command + [
                "--phase", "candidate", "--deck", str(candidate),
                "--baseline-evaluation", str(baseline_path),
                "--output-dir", str(candidate_dir), "--output", str(candidate_path),
            ],
            capture_output=True, text=True, check=False,
        )
        assert candidate_run.returncode == 0, candidate_run.stdout + candidate_run.stderr
        candidate_data = json.loads(candidate_path.read_text(encoding="utf-8"))
        assert candidate_data["valid"] is True, candidate_data
        assert candidate_data["observed"]["native_tables"] == 5, candidate_data
        assert candidate_data["observed"]["a_tbl_count"] == 5, candidate_data
        assert candidate_data["observed"]["policy_fee_table"]["merged_cells"] == [
            [1, 0, 2, 0], [3, 0, 4, 0], [5, 0, 6, 0], [7, 0, 8, 0]
        ], candidate_data
        assert candidate_data["text_audit"]["body_native_text"] is True, candidate_data
        proof_path = candidate_dir / "improvement.json"
        proof = subprocess.run([
            sys.executable, str(PROOF), "--baseline", str(baseline_path),
            "--candidate", str(candidate_path), "--case-spec", str(CASE),
            "--mode", "replay", "--report", str(proof_path),
        ], capture_output=True, text=True, check=False)
        assert proof.returncode == 0, proof.stdout + proof.stderr
        assert json.loads(proof_path.read_text(encoding="utf-8"))["promotion"] == "improved"
    print("social-channel-commission-native-01 case replay: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
