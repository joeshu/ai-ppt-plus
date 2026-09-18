#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from reconstruction.asset_job_runtime import AssetJobRuntime


def main() -> int:
    p = argparse.ArgumentParser(description="Register/review one deterministic ImageGen asset job without rerunning the whole slide.")
    p.add_argument("--job", required=True)
    p.add_argument("--run-root", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--slide-width-emu", type=int, required=True)
    p.add_argument("--slide-height-emu", type=int, required=True)
    p.add_argument("--receipt")
    p.add_argument("--review")
    p.add_argument("--render-context", default="default")
    args = p.parse_args()
    job = json.loads(Path(args.job).read_text(encoding="utf-8"))
    runtime = AssetJobRuntime(job, args.run_root, args.source, slide_size_emu=(args.slide_width_emu, args.slide_height_emu), render_context=args.render_context)
    if args.receipt:
        state = runtime.register(json.loads(Path(args.receipt).read_text(encoding="utf-8")))
    elif args.review:
        state = runtime.review(json.loads(Path(args.review).read_text(encoding="utf-8")))
    else:
        state = runtime.cache_hit() or runtime.load_state()
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
