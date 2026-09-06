#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "evals" / "fresh-12" / "fresh12.py"


def load_module():
    spec = importlib.util.spec_from_file_location("fresh12", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    fresh12 = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        suite = root / "suite.json"
        suite.write_text(json.dumps({
            "suite_id": "fresh12-test",
            "cases": [
                {"case_id": f"case-{index:02d}", "title": f"Case {index}", "prompt": f"prompt {index}"}
                for index in range(1, 13)
            ],
        }), encoding="utf-8")
        run_dir = root / "run"
        rc = fresh12.prepare(SimpleNamespace(suite=str(suite), run_dir=str(run_dir), run_id="test-run"))
        assert rc == 0
        manifest = json.loads((run_dir / "fresh12-run.json").read_text(encoding="utf-8"))
        assert manifest["case_count"] == 12
        assert manifest["editable_visual_authority"] == "current-run-fresh-image-only"
        assert all((run_dir / "cases" / f"case-{index:02d}" / "generation" / "request.json").is_file() for index in range(1, 13))

        report = root / "report.json"
        rc = fresh12.verify(SimpleNamespace(
            suite=str(suite),
            run_dir=str(run_dir),
            historical_dir=str(root / "historical"),
            report=str(report),
            strict=False,
        ))
        assert rc == 0
        evaluation = json.loads(report.read_text(encoding="utf-8"))
        assert evaluation["verdict"] == "INCOMPLETE"
        assert evaluation["complete_cases"] == 0
        assert evaluation["capability_judgement_allowed"] is False

        hits = fresh12.contamination_hits({
            "source": "evals/case-replay-12/visual/case-reference.png",
            "backend": "run_replay_suite.py:build_layout(case)",
        })
        assert "evals/case-replay-12/visual" in hits
        assert "run_replay_suite.py" in hits
        assert "build_layout(" in hits
    print("fresh12 protocol tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
