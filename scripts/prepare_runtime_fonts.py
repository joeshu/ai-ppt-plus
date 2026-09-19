#!/usr/bin/env python3
"""Materialize a task-local CJK font cache from system/runtime fonts.

The repository intentionally does not carry large TTF/TTC binaries. This helper
resolves installed fonts, copies only the regular/bold faces needed by text-fit
and strict authoring into an ignored runtime cache, and emits provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from runtime_fonts import resolve_font_file


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family", default="Noto Sans CJK SC")
    p.add_argument("--output-dir", default=".runtime/fonts")
    p.add_argument("--report", default=".runtime/font-runtime.json")
    a = p.parse_args()
    out = Path(a.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for bold, name in ((False, "NotoSansSC-Regular.ttf"), (True, "NotoSansSC-Bold.ttf")):
        source = resolve_font_file(a.family, bold=bold)
        if source is None:
            print(json.dumps({"valid": False, "code": "runtime_cjk_font_unresolved", "family": a.family}, ensure_ascii=False))
            return 2
        target = out / name
        shutil.copyfile(source, target)
        records.append({"role": "bold" if bold else "regular", "source": str(source), "target": str(target), "sha256": sha256(target)})
    report = {
        "schema": "ai-ppt-plus/runtime-font-materialization/v1",
        "valid": True,
        "family": a.family,
        "repository_font_binary_required": False,
        "runtime_cache": str(out),
        "files": records,
    }
    report_path = Path(a.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
