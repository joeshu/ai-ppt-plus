#!/usr/bin/env python3
"""Initialize the A4 visual-generation evidence manifest for this suite."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    plan_path = ROOT / "visual-generation-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest = {
        "schema": "ai-ppt-plus/visual-generation-manifest/v1",
        "project_id": plan["project_id"],
        "generator_skill": "ai-ppt-visual-gen",
        "tool_resolution": "runtime-discovery",
        "backend_policy": "raster-only",
        "source_retention": "generated-source-and-project-copy",
        "no_code_overlay": True,
        "plan_sha256": digest(plan_path),
        "generation_session_id": plan["generation_session"]["session_id"],
        "continuity_policy": plan["generation_session"]["continuity_policy"],
        "slides": [],
    }
    target = ROOT / "visual-generation-manifest.json"
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(target), "plan_sha256": manifest["plan_sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
