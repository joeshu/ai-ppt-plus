#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "evals" / "fresh-12" / "capability_gate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("fresh12_capability_gate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    gate = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "run"
        run_dir.mkdir()
        cases = [{"case_id": f"case-{index:02d}"} for index in range(1, 13)]
        (run_dir / "fresh12-run.json").write_text(json.dumps({
            "run_id": "fresh-test",
            "created_at": "2026-09-06T00:00:00+00:00",
            "cases": cases,
        }), encoding="utf-8")
        report = gate.evaluate(SimpleNamespace(
            run_dir=str(run_dir),
            historical_dir=str(root / "historical"),
            blurred_layout_ssim_min=0.90,
            global_ssim_min=0.82,
            pixel_fidelity_score_min=0.80,
        ))
        assert report["verdict"] == "INCOMPLETE"
        assert report["complete_cases"] == 0
        assert report["incomplete_cases"] == 12
        assert report["capability_judgement_allowed"] is False
        assert gate.contamination({"input": "references/old.png", "builder": "run_replay_suite.py build_layout(case)"})
    print("fresh12 capability gate tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
