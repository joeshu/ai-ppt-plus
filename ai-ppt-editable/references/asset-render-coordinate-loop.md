# Asset-to-Render Coordinate Loop

## Purpose

Close the coordinate gap between an independent transparent asset and what is actually visible in the final fresh PowerPoint render.

Asset QA alone is insufficient: an icon can have correct alpha, contour and color yet still be too small, shifted, clipped or visually off-center after placement. B5 therefore records the transform from asset alpha-space -> PPT slot-space -> final render-space.

## Required record

For each independently placed visual asset record:

- stable `object_id` and page;
- asset canvas size;
- alpha-visible bbox and alpha-weighted visual centroid;
- safe transparent padding;
- normalized PPT slot bbox;
- final render canvas size;
- observed visible bbox from the fresh render crop.

## Output

`scripts/asset_render_coordinate_loop.py` projects the alpha-visible geometry into render coordinates and emits:

- expected visible bbox;
- expected visual centroid;
- observed visible bbox;
- centroid delta in pixels;
- scale delta ratio;
- per-edge visible-bbox delta;
- proposed translation/scale repair;
- `regenerate_asset=false` for placement-only defects.

These numeric deltas are repair instructions, not visual release scores.

## Policy

1. Identity/color/contour defects belong to Asset Color/Identity Contract and may regenerate the asset.
2. Placement-only defects must repair slot/transform parameters first and must not consume ImageGen regeneration attempts.
3. Clipping must be diagnosed from the fresh final render, not only from the source PNG/contact sheet.
4. Repair must preserve protected neighbors and z-order.
5. No SSIM/IoU/0.90 threshold is introduced here.

## Usage

```bash
python3 scripts/asset_render_coordinate_loop.py PROJECT/asset-render-records.json \
  --report PROJECT/asset-render-coordinate-report.json --json
```

The report is then consumed by Responsible Object Repair / Protected Repair Planner.
