#!/usr/bin/env python3
"""Render PPTX with installed Microsoft PowerPoint on Windows."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    errors = []
    pages = []
    if os.name != "nt":
        errors.append("Microsoft PowerPoint export requires Windows")
    else:
        try:
            import win32com.client  # type: ignore
            args.output_dir.mkdir(parents=True, exist_ok=True)
            for stale in args.output_dir.glob("*.png"):
                stale.unlink()
            for stale in args.output_dir.glob("*.PNG"):
                stale.unlink()
            app = win32com.client.DispatchEx("PowerPoint.Application")
            presentation = None
            try:
                presentation = app.Presentations.Open(str(args.pptx.resolve()), WithWindow=False, ReadOnly=True)
                presentation.Export(str(args.output_dir.resolve()), "PNG", args.width, args.height)
            finally:
                if presentation is not None:
                    presentation.Close()
                app.Quit()
            exported = list(args.output_dir.glob("*.PNG")) + list(args.output_dir.glob("*.png"))
            exported.sort(key=lambda path: int((re.search(r"(\d+)$", path.stem) or re.search(r"(\d+)", path.stem)).group(1)))
            seen = set()
            for index, source in enumerate(exported, 1):
                if source.resolve() in seen:
                    continue
                seen.add(source.resolve())
                target = args.output_dir / f"slide-{index}.png"
                if source != target:
                    source.replace(target)
                from PIL import Image
                with Image.open(target) as image:
                    image.load()
                pages.append(str(target.resolve()))
            if not pages:
                errors.append("PowerPoint produced no PNG slides")
        except Exception as exc:
            errors.append(f"PowerPoint export failed: {type(exc).__name__}: {exc}")
    result = {"schema": "ai-ppt-plus/render/v1", "ok": not errors, "source": str(args.pptx.resolve()), "deck_sha256": sha256(args.pptx) if args.pptx.is_file() else None, "renderer": "powerpoint-export", "pages": pages, "errors": errors}
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
