#!/usr/bin/env python3
"""Fail reconstruction when any declared hard region has poor local fidelity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from skimage.metrics import structural_similarity as ssim


def _box_px(box, width, height):
    x, y, w, h = [float(v) for v in box]
    if max(abs(x), abs(y), abs(w), abs(h)) <= 1.5:
        x, w = x * width, w * width
        y, h = y * height, h * height
    x0 = max(0, min(width - 1, int(round(x))))
    y0 = max(0, min(height - 1, int(round(y))))
    x1 = max(x0 + 1, min(width, int(round(x + w))))
    y1 = max(y0 + 1, min(height, int(round(y + h))))
    return x0, y0, x1, y1


def _score(a: Image.Image, b: Image.Image) -> dict:
    if b.size != a.size:
        b = b.resize(a.size, Image.Resampling.LANCZOS)
    aa, bb = np.asarray(a.convert('RGB')), np.asarray(b.convert('RGB'))
    raw = float(ssim(aa, bb, channel_axis=2, data_range=255))
    ba = np.asarray(a.filter(ImageFilter.GaussianBlur(3)).convert('RGB'))
    bb2 = np.asarray(b.filter(ImageFilter.GaussianBlur(3)).convert('RGB'))
    layout = float(ssim(ba, bb2, channel_axis=2, data_range=255))
    pixel = float(1.0 - np.abs(ba.astype(np.float32) - bb2.astype(np.float32)).mean() / 255.0)
    return {'ssim': raw, 'layout_ssim': layout, 'pixel_fidelity': pixel}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--regions', type=Path, required=True, help='JSON with regions[{id,bbox,min_layout_ssim,min_pixel_fidelity}]')
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args()
    source = Image.open(args.source).convert('RGB')
    candidate = Image.open(args.candidate).convert('RGB').resize(source.size, Image.Resampling.LANCZOS)
    spec = json.loads(args.regions.read_text(encoding='utf-8'))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows=[]
    for index, region in enumerate(spec.get('regions') or [], 1):
        rid=str(region.get('id') or f'region-{index}')
        box=_box_px(region['bbox'], *source.size)
        src=source.crop(box); cand=candidate.crop(box)
        scores=_score(src,cand)
        min_layout=float(region.get('min_layout_ssim',0.90)); min_pixel=float(region.get('min_pixel_fidelity',0.90))
        valid=scores['layout_ssim']>=min_layout and scores['pixel_fidelity']>=min_pixel
        src_path=args.output_dir/f'{index:02d}-{rid}-source.png'; cand_path=args.output_dir/f'{index:02d}-{rid}-candidate.png'
        src.save(src_path); cand.save(cand_path)
        rows.append({'id':rid,'bbox_px':list(box),'scores':scores,'thresholds':{'layout_ssim':min_layout,'pixel_fidelity':min_pixel},'valid':valid,'source_crop':str(src_path),'candidate_crop':str(cand_path),'repair_trace':[] if valid else ['local_crop']})
    failures=[r for r in rows if not r['valid']]
    worst=min(rows,key=lambda r:min(r['scores']['layout_ssim']-r['thresholds']['layout_ssim'],r['scores']['pixel_fidelity']-r['thresholds']['pixel_fidelity'])) if rows else None
    report={'schema':'ai-ppt-plus/hard-region-crop-gate/v1','valid':bool(rows) and not failures,'region_count':len(rows),'failure_count':len(failures),'worst_region':worst['id'] if worst else None,'regions':rows}
    args.report.parent.mkdir(parents=True,exist_ok=True); args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('schema','valid','region_count','failure_count','worst_region')},ensure_ascii=False))
    return 0 if report['valid'] else 3

if __name__=='__main__':
    raise SystemExit(main())
