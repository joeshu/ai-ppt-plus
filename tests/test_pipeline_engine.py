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
        checkpoint = json.loads((root / "run-2/pipeline-checkpoint.json").read_text(encoding="utf-8"))
        assert checkpoint["schema"] == "ai-ppt-plus/pipeline-checkpoint/v2" and checkpoint["status"] == "completed"
        resumed_executor = PipelineExecutor(root / "run-2", mode="dag", cache_dir=cache, max_workers=1, resume=True)
        resumed_report = root / "run-2/probe.json"
        resumed_executor.add(PipelineTask("probe", [str(ROOT / "scripts/probe_environment.py"), "--output", str(resumed_report)], outputs=(resumed_report,), inputs=(source,), metadata={"fixture": "pipeline-engine"}))
        resumed = resumed_executor.run()
        assert resumed[0]["resumed"] is True and resumed_executor.last_resume_hits == 1

        resumed_report.write_text("corrupt", encoding="utf-8")
        repaired = run_probe(root / "run-2", cache, source)
        assert repaired[0]["ok"] is True

        cache_artifact = cache / first[0]["cache_key"] / "artifacts" / "probe.json"
        cache_artifact.write_text(cache_artifact.read_text(encoding="utf-8") + "\ncorrupted", encoding="utf-8")
        corrupted = run_probe(root / "run-corrupted", cache, source)
        assert corrupted[0]["ok"] is True and corrupted[0]["cache_hit"] is False
        assert list(cache.glob(".corrupt-*")), "corrupt cache entry must be quarantined"

        source.write_text("v2", encoding="utf-8")
        third = run_probe(root / "run-3", cache, source)
        assert third[0]["ok"] is True and third[0]["cache_hit"] is False

        missing_output = PipelineExecutor(root / "missing-output", mode="dag", cache_dir=cache, max_workers=1)
        missing_output.add(PipelineTask("incomplete", outputs=(root / "missing-output/result.json",), static_result={"ok": True}))
        incomplete = missing_output.run()
        assert incomplete[0]["ok"] is True and not (cache / incomplete[0]["cache_key"]).exists()
        assert (root / "missing-output/result.json").is_file()
        assert json.loads((root / "missing-output/result.json").read_text(encoding="utf-8"))["valid"] is True

        declared_missing = PipelineExecutor(root / "declared-missing", mode="dag", cache_dir=cache, max_workers=1)
        missing_path = root / "declared-missing/never-created.json"
        declared_missing.add(PipelineTask(
            "declared-missing",
            ["-c", "pass"],
            outputs=(missing_path,),
        ))
        missing_result = declared_missing.run()[0]
        assert missing_result["ok"] is False
        assert missing_result["failure"] == "declared_output_missing"
        assert missing_result["missing_outputs"] == [str(missing_path)]
        assert not (cache / missing_result["cache_key"]).exists()

        parallel = PipelineExecutor(root / "parallel", mode="dag", cache_dir=root / "parallel-cache", max_workers=2)
        parallel.add(PipelineTask("a", [str(ROOT / "scripts/probe_environment.py"), "--output", str(root / "parallel/a.json")], outputs=(root / "parallel/a.json",)))
        parallel.add(PipelineTask("b", [str(ROOT / "scripts/probe_environment.py"), "--output", str(root / "parallel/b.json")], outputs=(root / "parallel/b.json",)))
        parallel.add(PipelineTask("c", [str(ROOT / "scripts/probe_environment.py"), "--output", str(root / "parallel/c.json")], deps=("a", "b"), outputs=(root / "parallel/c.json",)))
        results = parallel.run()
        assert all(item["ok"] for item in results)
        assert results[2]["deps"] == ["a", "b"]

        attempts = root / "attempts.txt"
        retry = PipelineExecutor(root / "retry", mode="dag", cache_dir=root / "retry-cache", max_workers=1)
        retry.add(PipelineTask("bounded-retry", ["-c", f"from pathlib import Path; p=Path({str(attempts)!r}); n=int(p.read_text()) if p.exists() else 0; p.write_text(str(n+1)); raise OSError('transient')"], max_retries=2, retry_failures=("command-failed",)))
        retry_result = retry.run()[0]
        assert retry_result["ok"] is False and retry_result["retry_count"] == 2
        assert attempts.read_text() == "3"
    print("pipeline DAG/cache contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
