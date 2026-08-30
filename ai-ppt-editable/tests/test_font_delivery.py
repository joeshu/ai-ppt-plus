"""Regression test for the portable three-signal font delivery gate."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="font-delivery-") as temp:
        work = Path(temp)
        write(work / "font.json", {"ok": True, "cjk_delivery_supported": True, "fonts": [{"requested": "Noto Sans CJK SC", "resolved": "Noto Sans CJK SC", "exact_or_family_match": True}]})
        write(work / "asset.json", {"valid": True})
        write(work / "inspection.json", {"embedded_fonts": {"present": True}})
        write(work / "render.json", {"ok": True, "pages": ["slide-1.png"]})
        write(work / "visual.json", {"valid": True, "pages": [{"stats": {"nonuniform": True}}]})
        report = work / "report.json"
        command = [sys.executable, str(root / "scripts/validate_font_delivery.py"), "--font-report", str(work / "font.json"), "--font-asset-report", str(work / "asset.json"), "--inspection", str(work / "inspection.json"), "--render-report", str(work / "render.json"), "--render-visual-gate", str(work / "visual.json"), "--require-embedded", "--report", str(report)]
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert json.loads(report.read_text(encoding="utf-8"))["valid"] is True
        write(work / "inspection-bad.json", {"embedded_fonts": {"present": False}})
        bad_command = [item if item != str(work / "inspection.json") else str(work / "inspection-bad.json") for item in command]
        bad_report = work / "bad-report.json"
        bad_command[bad_command.index("--report") + 1] = str(bad_report)
        failed = subprocess.run(bad_command, cwd=root, capture_output=True, text=True, check=False)
        assert failed.returncode == 2
        bad_data = json.loads(bad_report.read_text(encoding="utf-8"))
        assert "embedded_font_missing" in {item["code"] for item in bad_data["issues"]}
    print("portable font delivery triple gate: ok")


if __name__ == "__main__":
    main()