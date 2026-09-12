#!/usr/bin/env python3
"""End-to-end cache, incremental and forced-interruption recovery proof."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from pipeline_engine import PipelineExecutor, PipelineTask


def task_command(source: Path, output: Path, delay: float = 0.08) -> list[str]:
    code = (
        "import pathlib,time; "
        f"time.sleep({delay}); "
        f"s=pathlib.Path({str(source)!r}); o=pathlib.Path({str(output)!r}); "
        "o.parent.mkdir(parents=True,exist_ok=True); o.write_text(s.read_text())"
    )
    return ["-c", code]


def build(run: Path, cache: Path, sources: list[Path], *, resume: bool = False, slow_last: bool = False) -> PipelineExecutor:
    engine = PipelineExecutor(run, mode="dag", cache_dir=cache, max_workers=2, resume=resume)
    for index, source in enumerate(sources, 1):
        output = run / f"page-{index}.json"
        engine.add(PipelineTask(f"page-{index}", task_command(source, output, 20.0 if slow_last and index == len(sources) else 0.08), outputs=(output,), inputs=(source,)))
    return engine


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pipeline-recovery-performance-") as temp:
        root = Path(temp)
        cache = root / "cache"
        sources = []
        for index in range(1, 6):
            source = root / f"source-{index}.txt"
            source.write_text(f"page-{index}", encoding="utf-8")
            sources.append(source)

        cold_engine = build(root / "cold", cache, sources)
        cold_engine.run()
        hot_engine = build(root / "hot", cache, sources)
        hot_results = hot_engine.run()
        assert all(item["cache_hit"] for item in hot_results)
        assert hot_engine.last_wall_duration_ms < cold_engine.last_wall_duration_ms * 0.7

        sources[1].write_text("page-2-modified", encoding="utf-8")
        incremental_engine = build(root / "incremental", cache, sources)
        incremental = incremental_engine.run()
        misses = [item["name"] for item in incremental if not item["cache_hit"]]
        assert misses == ["page-2"], misses
        assert incremental_engine.last_cache_hits == 4
        assert incremental_engine.last_wall_duration_ms < cold_engine.last_wall_duration_ms * 0.6

        interrupted_run = root / "interrupted"
        driver = root / "interrupt_driver.py"
        verified_output = interrupted_run / "verified.json"
        verified_code = f"from pathlib import Path; Path({str(verified_output)!r}).write_text('ok')"
        driver.write_text(
            "import sys\nfrom pathlib import Path\n"
            f"sys.path.insert(0,{str(ROOT / 'scripts')!r})\n"
            "from pipeline_engine import PipelineExecutor,PipelineTask\n"
            f"r=Path({str(interrupted_run)!r}); c=Path({str(root / 'interrupt-cache')!r}); s=Path({str(sources[0])!r})\n"
            "e=PipelineExecutor(r,mode='dag',cache_dir=c,max_workers=1)\n"
            f"e.add(PipelineTask('verified',['-c',{verified_code!r}],outputs=(r/'verified.json',),inputs=(s,)))\n"
            "e.add(PipelineTask('slow',['-c','import time; time.sleep(20)'],deps=('verified',)))\n"
            "e.run()\n",
            encoding="utf-8",
        )
        process = subprocess.Popen([sys.executable, str(driver)])
        checkpoint = interrupted_run / "pipeline-checkpoint.json"
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if checkpoint.is_file():
                data = json.loads(checkpoint.read_text(encoding="utf-8"))
                if any(item.get("name") == "verified" for item in data.get("completed", [])):
                    break
            time.sleep(0.05)
        else:
            process.terminate(); process.wait(timeout=5)
            raise AssertionError("verified checkpoint was not published before timeout")
        process.terminate(); process.wait(timeout=5)

        resumed = PipelineExecutor(interrupted_run, mode="dag", cache_dir=root / "interrupt-cache", max_workers=1, resume=True)
        resumed.add(PipelineTask("verified", ["-c", verified_code], outputs=(verified_output,), inputs=(sources[0],)))
        resumed.add(PipelineTask("slow", ["-c", "pass"], deps=("verified",)))
        results = resumed.run()
        assert results[0].get("resumed") is True and results[1]["ok"] is True
        assert resumed.last_resume_hits == 1

        report = {
            "schema": "ai-ppt-plus/recovery-performance-proof/v1",
            "status": "passed",
            "cold_ms": cold_engine.last_wall_duration_ms,
            "hot_ms": hot_engine.last_wall_duration_ms,
            "hot_improvement": round(1 - hot_engine.last_wall_duration_ms / cold_engine.last_wall_duration_ms, 6),
            "incremental_ms": incremental_engine.last_wall_duration_ms,
            "incremental_improvement": round(1 - incremental_engine.last_wall_duration_ms / cold_engine.last_wall_duration_ms, 6),
            "incremental_cache_hit_rate": incremental_engine.last_cache_hits / 5,
            "incremental_recomputed": misses,
            "forced_termination_resume_hits": resumed.last_resume_hits,
        }
        print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
