#!/usr/bin/env python3
"""Regression coverage for exact reference-ledger to PPTX text comparison."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "text_ledger.py"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def make_pptx(path: Path) -> None:
    xml = f'''<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="{A}">
      <p:cSld><p:spTree><p:sp><p:txBody>
        <a:p><a:r><a:t>标题</a:t></a:r></a:p>
        <a:p><a:r><a:t>90分</a:t></a:r></a:p>
      </p:txBody></p:sp></p:spTree></p:cSld>
    </p:sld>'''.encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/slides/slide1.xml", xml)


def invoke(pptx: Path, ledger: Path, report: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--pptx", str(pptx), "--ledger", str(ledger), "--strict", "--output", str(report)],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        pptx = folder / "sample.pptx"
        make_pptx(pptx)
        ledger = folder / "ledger.json"
        ledger.write_text(json.dumps({"entries": [
            {"page": 1, "region": "title", "text": "标题", "human_verified": True, "ocr_confidence": 1.0},
            {"page": 1, "region": "score", "text": "90分", "human_verified": True, "ocr_confidence": 1.0},
        ]}, ensure_ascii=False), encoding="utf-8")
        report = folder / "report.json"
        completed = invoke(pptx, ledger, report)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        result = json.loads(report.read_text(encoding="utf-8"))
        assert result["valid"] is True
        assert result["entry_count"] == 2

        ledger.write_text(json.dumps({"entries": [{"page": 1, "text": "91分", "human_verified": True}]}, ensure_ascii=False), encoding="utf-8")
        failed = invoke(pptx, ledger, folder / "failed.json")
        assert failed.returncode != 0
        result = json.loads((folder / "failed.json").read_text(encoding="utf-8"))
        assert any(item["code"] == "reference_text_missing_or_different" for item in result["issues"])
    print("text ledger character gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
