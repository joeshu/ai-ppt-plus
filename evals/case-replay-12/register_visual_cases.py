#!/usr/bin/env python3
"""Register the 12 native imagegen outputs using the visual-gen A4 helper."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REGISTER = ROOT.parents[1] / "ai-ppt-visual-gen" / "scripts" / "register_generated_slide.py"


def main():
    suite = json.loads((ROOT / "case-suite.json").read_text(encoding="utf-8"))
    source_dir = ROOT / "visual" / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    generated_dir = ROOT / "visual" / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    for index, case in enumerate(suite["cases"], start=1):
        case_id = case["case_id"]
        source = ROOT / "visual" / f"{case_id}-reference.png"
        retained_source = source_dir / f"{case_id}.png"
        shutil.copy2(source, retained_source)
        copy_to = Path("visual/generated") / f"{case_id}.png"
        command = [
            sys.executable,
            str(REGISTER),
            str(ROOT / "visual-generation-manifest.json"),
            "--slide-no", str(index),
            "--prompt-file", f"prompts/{index:02d}-{case_id}.md",
            "--source", str(retained_source.relative_to(ROOT)),
            "--copy-to", str(copy_to),
            "--backend", "runtime-discovered-raster-imagegen",
            "--model-or-tool", "imagegen",
            "--session-id", "case-replay-12-imagegen-session-R1",
            "--context-continuity-status", "preserved",
            "--attempt", "1",
        ]
        subprocess.run(command, cwd=ROOT, check=True)
    print(json.dumps({"registered_slides": len(suite["cases"]), "manifest": str(ROOT / "visual-generation-manifest.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
