#!/usr/bin/env python3
"""Preflight planned builds/renders and recorded ImageGen retries."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from atomic_output import atomic_write_json
from execution_budget import imagegen_usage,validate_usage

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--profile",choices=("fast","strict","ci"),default="fast"); p.add_argument("--project",type=Path,required=True); p.add_argument("--candidate-build-count",type=int,default=1); p.add_argument("--full-render-count",type=int,default=1); p.add_argument("--report",type=Path,required=True); p.add_argument("--non-delivery",action="store_true"); a=p.parse_args()
    calls,retries=imagegen_usage(a.project.resolve())
    result=validate_usage(a.profile,candidate_build_count=max(0,a.candidate_build_count),full_render_count=max(0,a.full_render_count),imagegen_call_count=calls,imagegen_retry_counts=retries,delivery=not a.non_delivery)
    atomic_write_json(a.report.resolve(),result); print(json.dumps(result,ensure_ascii=False)); return 0 if result["valid"] else 2
if __name__=="__main__": raise SystemExit(main())

