#!/usr/bin/env python3
"""Prefer PowerPoint export; label LibreOffice output as provisional evidence."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run(command: list[str]) -> tuple[int, dict]:
    result = subprocess.run(command, capture_output=True, text=True)
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception:
        payload = {"ok": False, "errors": [result.stderr or result.stdout or "renderer produced no JSON"]}
    return result.returncode, payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--backend", choices=("auto", "powerpoint", "libreoffice"), default="auto")
    parser.add_argument("--fallback-policy", choices=("provisional", "forbid"), default=os.environ.get("AI_PPT_POWERPOINT_FALLBACK", "provisional"))
    parser.add_argument("--require-powerpoint", action="store_true", help="forbid LibreOffice fallback")
    parser.add_argument("--dpi", type=int, default=144)
    parser.add_argument("--pages")
    parser.add_argument("--font-dir")
    parser.add_argument("--page-cache-dir")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.require_powerpoint:
        args.fallback_policy = "forbid"
    scripts = Path(__file__).resolve().parent
    attempts = []
    result = None
    if args.backend in {"auto", "powerpoint"}:
        if os.name == "nt":
            code, payload = run([sys.executable, str(scripts / "render_powerpoint.py"), str(args.pptx), "--output-dir", str(args.output_dir)])
            attempts.append({"backend": "powerpoint", "exit_code": code, "ok": payload.get("ok", False)})
            if code == 0 and payload.get("ok"):
                result = payload
        elif args.backend == "powerpoint":
            attempts.append({"backend": "powerpoint", "exit_code": 2, "ok": False, "reason": "not_windows"})
    if result is None and args.backend in {"auto", "libreoffice"} and not (args.backend == "auto" and args.fallback_policy == "forbid"):
        command = [sys.executable, str(scripts / "render_pptx.py"), str(args.pptx), "--output-dir", str(args.output_dir), "--dpi", str(args.dpi)]
        if args.font_dir:
            command += ["--font-dir", args.font_dir]
        if args.page_cache_dir:
            command += ["--page-cache-dir", args.page_cache_dir]
        if args.pages:
            command += ["--pages", args.pages]
        code, payload = run(command)
        attempts.append({"backend": "libreoffice", "exit_code": code, "ok": payload.get("ok", False)})
        result = payload
    if result is None:
        result = {"schema": "ai-ppt-plus/render/v1", "ok": False, "renderer": None, "pages": [], "errors": ["requested authoritative renderer unavailable"]}
    is_powerpoint = str(result.get("renderer") or "").lower() == "powerpoint-export"
    result["renderer_policy"] = "powerpoint-final-libreoffice-provisional"
    result["authoritative_visual_evidence"] = is_powerpoint
    result["visual_acceptance_status"] = "final" if is_powerpoint else ("provisional" if result.get("ok") else "blocked")
    result["renderer_role"] = "final_acceptance" if is_powerpoint else ("diagnostic_preview" if result.get("ok") else "unavailable")
    result["powerpoint_required_for_final_signoff"] = True
    result["backend_attempts"] = attempts
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
