#!/usr/bin/env python3
"""Build a portable, hash-indexed project review package."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from atomic_output import atomic_write_json, atomic_write_text


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def copy_record(source: Path, root: Path, output: Path, records: list[dict[str, Any]]) -> None:
    if not source.is_file():
        return
    try:
        relative = source.resolve().relative_to(root.resolve())
    except ValueError:
        relative = Path(source.name)
    target = output / "artifacts" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    records.append({"path": str(target.relative_to(output)), "source": str(source), "sha256": digest(target), "size": target.stat().st_size})


def build(pipeline_result: Path, output: Path) -> dict[str, Any]:
    data = json.loads(pipeline_result.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("pipeline result must be an object")
    run_dir = Path(str(data.get("run_dir") or pipeline_result.parent)).resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for candidate in (
        pipeline_result,
        run_dir / "review.html",
        run_dir / "report-index.json",
        run_dir / "project-report.json",
        run_dir / "report-bundle-validation.json",
        run_dir / "pipeline-checkpoint.json",
    ):
        copy_record(candidate, run_dir, output, records)
    rendered = run_dir / "rendered"
    if rendered.is_dir():
        for candidate in sorted(rendered.glob("slide-*.png")):
            copy_record(candidate, run_dir, output, records)
    summary = "# AI PPT Plus 审阅包\n\n"
    summary += f"- 项目：`{data.get('project')}`\n- 运行：`{data.get('run_id')}`\n"
    summary += f"- 技术状态：`{data.get('technical_status')}`\n- 人工状态：`{data.get('human_review_status')}`\n- 交付状态：`{data.get('release_status')}`\n"
    summary += f"- 验证范围：`{data.get('validation_scope')}`\n- 失败步骤：`{', '.join(data.get('failed_steps') or []) or '无'}`\n\n"
    summary += "审阅顺序：先看渲染页，再看质量证据和失败步骤；技术通过不等于人工收口完成。\n"
    atomic_write_text(output / "README.md", summary)
    records.append({"path": "README.md", "source": "generated", "sha256": digest(output / "README.md"), "size": (output / "README.md").stat().st_size})
    manifest = {
        "schema": "ai-ppt-plus/review-package/v1",
        "project": data.get("project"),
        "run_id": data.get("run_id"),
        "pipeline_result_sha256": digest(pipeline_result),
        "technical_valid": data.get("technical_valid"),
        "human_review_status": data.get("human_review_status"),
        "release_eligible": data.get("release_eligible"),
        "artifact_count": len(records),
        "artifacts": records,
    }
    atomic_write_json(output / "review-package.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pipeline_result")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = build(Path(args.pipeline_result).resolve(), Path(args.output).resolve())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": "ai-ppt-plus/review-package/v1", "valid": False, "code": "review_package_failed", "message": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"schema": "ai-ppt-plus/review-package/v1", "valid": True, "output": str(Path(args.output).resolve()), "artifact_count": result["artifact_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
