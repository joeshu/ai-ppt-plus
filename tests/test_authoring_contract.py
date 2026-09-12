#!/usr/bin/env python3
"""Regression coverage for the strict JS ESM/artifact-tool authoring gate."""
from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_authoring_contract.py"
SHA = "5377f8c5e1edf4b4481a344637027b9748e507ff"


def invoke(builder: Path, output: Path, qa: Path, report: Path, receipt: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable, str(SCRIPT), "--builder", str(builder), "--output", str(output), "--report", str(report),
        "--repo-sha", SHA, "--qa-dir", str(qa), "--marker-count", "1", "--strict",
    ]
    if receipt:
        command.extend(["--finalizer-receipt", str(receipt)])
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        qa = folder / "qa"
        qa.mkdir()
        output = folder / "final.pptx"
        output.write_bytes(b"pptx-placeholder")
        builder = folder / "build.mjs"
        builder.write_text('import "@oai/artifact-tool"; await PresentationFile.exportPptx();', encoding="utf-8")
        report = folder / "report.json"
        completed = invoke(builder, output, qa, report)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert json.loads(report.read_text(encoding="utf-8"))["valid"] is True

        output_sha = hashlib.sha256(output.read_bytes()).hexdigest()
        receipt = folder / "receipt.json"
        receipt.write_text(json.dumps({"finalSha256": output_sha, "firstPartyImport": {"sha256": output_sha}}), encoding="utf-8")
        receipt_report = folder / "receipt-report.json"
        completed = invoke(builder, output, qa, receipt_report, receipt)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert json.loads(receipt_report.read_text(encoding="utf-8"))["valid"] is True
        receipt.write_text(json.dumps({"finalSha256": "0" * 64, "firstPartyImport": {"sha256": "0" * 64}}), encoding="utf-8")
        mismatch_report = folder / "mismatch-report.json"
        failed = invoke(builder, output, qa, mismatch_report, receipt)
        assert failed.returncode != 0
        mismatch = json.loads(mismatch_report.read_text(encoding="utf-8"))
        assert "finalizer_output_hash_mismatch" in {item["code"] for item in mismatch["issues"]}

        # The production builder resolves the package through a same-directory
        # ESM runtime adapter; that transitive binding is accepted only when
        # the adapter itself names the required package.
        adapter_builder = folder / "adapter-build.mjs"
        adapter_builder.write_text('import { loadArtifactTool } from "./artifact_tool_runtime.mjs"; await PresentationFile.exportPptx();', encoding="utf-8")
        (folder / "artifact_tool_runtime.mjs").write_text('const packageName = "@oai/artifact-tool"; export { packageName, loadArtifactTool };', encoding="utf-8")
        adapter_report = folder / "adapter-report.json"
        completed = invoke(adapter_builder, output, qa, adapter_report)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        adapter_result = json.loads(adapter_report.read_text(encoding="utf-8"))
        assert adapter_result["valid"] is True
        assert adapter_result["artifact_tool_resolution"]["source"] == "same-directory-runtime-adapter"

        builder.write_text('import "python-pptx"; await PresentationFile.exportPptx();', encoding="utf-8")
        failed = invoke(builder, output, qa, folder / "invalid.json")
        assert failed.returncode != 0
        result = json.loads((folder / "invalid.json").read_text(encoding="utf-8"))
        assert any(item["code"] == "forbidden_authoring_backend" for item in result["issues"])
    print("strict authoring contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
