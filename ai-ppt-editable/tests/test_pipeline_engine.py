#!/usr/bin/env python3
"""Regression tests for DAG ordering, cache restoration and input hashing."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pipeline_engine import PipelineExecutor, PipelineTask


ROOT = Path(__file__).resolve().parents[1]


def run_probe(run_dir: Path, cache_dir: Path, input_path: Path) -> list[dict]:
    executor = PipelineExecutor(run_dir, mode="dag", cache_dir=cache_dir, max_workers=3)
    report = run_dir / "probe.json"
    executor.add(PipelineTask(
        "probe",
        [str(ROOT / "scripts/probe_environment.py"), "--output", str(report)],
        outputs=(report,),
        inputs=(input_path,),
        metadata={"fixture": "pipeline-engine"},
    ))
    return executor.run()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pipeline-engine-") as temp:
        root = Path(temp)
        cache = root / "cache"
        source = root / "source.txt"
        source.write_text("v1", encoding="utf-8")
        first = run_probe(root / "run-1", cache, source)
        assert first[0]["ok"] is True and first[0]["cache_hit"] is False
        assert first[0]["duration_ms"] >= 0 and first[0]["cache_key"]

        second = run_probe(root / "run-2", cache, source)
        assert second[0]["ok"] is True and second[0]["cache_hit"] is True
        assert json.loads((root / "run-2/probe.json").read_text(encoding="utf-8"))["schema"] == "ai-ppt-plus/environment-report/v1"

        cache_artifact = cache / first[0]["cache_key"] / "artifacts" / "probe.json"
        cache_artifact.write_text(cache_artifact.read_text(encoding="utf-8") + "\ncorrupted", encoding="utf-8")
        corrupted = run_probe(root / "run-corrupted", cache, source)
        assert corrupted[0]["ok"] is True and corrupted[0]["cache_hit"] is False

        source.write_text("v2", encoding="utf-8")
        third = run_probe(root / "run-3", cache, source)
        assert third[0]["ok"] is True and third[0]["cache_hit"] is False

        missing_output = PipelineExecutor(root / "missing-output", mode="dag", cache_dir=cache, max_workers=1)
        missing_output.add(PipelineTask("incomplete", outputs=(root / "missing-output/result.json",), static_result={"ok": True}))
        incomplete = missing_output.run()
        assert incomplete[0]["ok"] is True and not (cache / incomplete[0]["cache_key"]).exists()
        assert (root / "missing-output/result.json").is_file()
        assert json.loads((root / "missing-output/result.json").read_text(encoding="utf-8"))["valid"] is True

        parallel = PipelineExecutor(root / "parallel", mode="dag", cache_dir=root / "parallel-cache", max_workers=2)
        parallel.add(PipelineTask("a", [str(ROOT / "scripts/probe_environment.py"), "--output", str(root / "parallel/a.json")], outputs=(root / "parallel/a.json",)))
        parallel.add(PipelineTask("b", [str(ROOT / "scripts/probe_environment.py"), "--output", str(root / "parallel/b.json")], outputs=(root / "parallel/b.json",)))
        parallel.add(PipelineTask("c", [str(ROOT / "scripts/probe_environment.py"), "--output", str(root / "parallel/c.json")], deps=("a", "b"), outputs=(root / "parallel/c.json",)))
        results = parallel.run()
        assert all(item["ok"] for item in results)
        assert results[2]["deps"] == ["a", "b"]
    print("pipeline DAG/cache contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
