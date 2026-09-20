# Asset-to-Render Coordinate Loop

The B5 loop closes the coordinate gap between an independent transparent asset,
its normalized PowerPoint slot and the fresh final render. Asset QA alone cannot
detect a correctly generated icon that is shifted, too small or clipped after
placement.

Each record declares `object_id`, page, asset canvas/alpha geometry, normalized
slot bbox, render canvas and the observed visible bbox from the fresh render.
When `--auto-bind-asset-qa` is enabled, the runner reads the real RGBA file and
binds alpha bbox, alpha-weighted centroid, safe padding and coverage. It can
also bind a `transparent-asset-qa` report by asset id or path.

The report contains the projected visible bbox and centroid, per-edge deltas,
scale delta, a placement-only translation/scale proposal and
`regenerate_asset=false`. If a fresh render directory is supplied, the runner
resolves `slide-N.png` and captures an object crop with the final page hash.
Those values are evidence for Responsible Object Repair, not a universal visual
score or release threshold.

Policy:

1. Identity, contour and color defects stay in the Asset Color/Identity
   Contract and may request an asset regeneration.
2. Placement-only defects repair slot/transform parameters first and do not
   consume ImageGen regeneration attempts.
3. Clipping is diagnosed from a fresh render and its crop, not a contact sheet.
4. Any repair must preserve protected neighbors and z-order.
5. A valid B5 report may still set `repair_loop_required=true` when it emits a
   non-zero placement delta; the pipeline remains in a repair state until B6
   or human review resolves it.

Example:

```bash
python3 scripts/asset_render_coordinate_loop.py project/asset-render-records.json \
  --base-dir project --render-dir run/rendered \
  --capture-crops run/asset-render-crops \
  --auto-bind-asset-qa \
  --report run/asset-render-coordinate-report.json
```
