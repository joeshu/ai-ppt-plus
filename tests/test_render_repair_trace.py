#!/usr/bin/env python3
"""Regression proof for crop-driven object Repair Trace planning."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from build_render_repair_trace import build_trace  # noqa:E402


def main()->int:
    layout={
        "slides":[{
            "texts":[{"object_id":"card2_body","text":"body","x":0.1,"y":0.2,"w":0.3,"h":0.2}],
            "charts":[{"object_id":"trend_chart","x":0.4,"y":0.1,"w":0.5,"h":0.3}],
            "images":[{"object_id":"brand_lockup","x":0.8,"y":0.01,"w":0.15,"h":0.08}],
        }]
    }
    regional={
        "foreground_weighted_score":0.62,
        "regions":[
            {"region_id":"s1:texts:card2_body","score":0.50,"bbox":[0.1,0.2,0.3,0.2],"bbox_px":[100,200,400,400],"metrics":{"global_ssim":0.45,"layout_ssim":0.48,"pixel_fidelity":0.72},"crop_evidence":{"reference_crop":"r.png","candidate_crop":"c.png","difference_crop":"d.png"}},
            {"region_id":"s1:charts:trend_chart","score":0.60,"bbox":[0.4,0.1,0.5,0.3],"metrics":{"global_ssim":0.55,"layout_ssim":0.58,"pixel_fidelity":0.77}},
            {"region_id":"s1:images:brand_lockup","score":0.92,"bbox":[0.8,0.01,0.15,0.08],"metrics":{"global_ssim":0.90,"layout_ssim":0.93,"pixel_fidelity":0.94}},
        ],
        "issues":[],
    }
    trace=build_trace(layout,regional,target=0.90,max_actions=10)
    assert trace["valid"]
    assert [a["object_id"] for a in trace["pending_actions"]]==["card2_body","trend_chart"]
    first=trace["pending_actions"][0]
    assert first["responsibility"]=="typography"
    assert first["auto_patch_allowed"] is False
    assert first["crop_evidence"]["reference_crop"]=="r.png"
    assert "geometry/margins before font shrink" in trace["policy"]
    print("crop-driven render Repair Trace: ok")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
