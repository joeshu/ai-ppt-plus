# Dense single-slide reconstruction

Use this short loop for dense 16:9 dashboard, strategy-map and operating-model
slides whose reference combines a chart, repeated cards, management bands and
footer decoration.

## Fast decomposition

1. Freeze the source dimensions and author in one pixel coordinate space using
   `ref_width` and `ref_height`. Convert to slide units only in the authoring
   backend.
   Hash every newly attached file first. If its bytes match an earlier source,
   reuse the verified text/geometry inventory and independently validated
   ImageGen assets by source and asset hash. Rebuild only regions affected by
   the user's latest feedback, then render and inspect the complete final slide.
2. Inventory large regions first: header/brand, status block, chart, repeated
   modules, guarantee band, results band and footer. Then assign stable IDs to
   their children. This prevents repeated OCR/layout passes.
3. Classify repeated icon-title-body modules as component groups, not tables.
   A visible grid is not table semantics.
4. Keep formal text in native text boxes. Keep cards, dividers, chart lines,
   markers, arrows and simple ribbons as native geometry. A full-slide raster
   is forbidden.
5. For narrow gradient headers, assign the main heading and compact qualifier
   separate nonoverlapping slots with a visible gap. Measure both with the
   delivery font before export and inspect the whole header crop after render;
   auto-shrink alone cannot repair overlapping slots.

## Chart uncertainty

Use a native chart only when every category and value is verified. When a
reference image has missing, occluded, duplicated or contradictory labels,
author the visible trend as editable static line/marker primitives and record
`visual_transcription_unverified` in notes/evidence. Never invent authoritative
values to satisfy a native chart schema. Preserve visibly duplicated labels
until the user confirms a correction.

## Fonts and icons

Run CJK font discovery before text fitting or visual preview. If no licensed
CJK font with the required glyph coverage is available:

- do not interpret blank glyphs, tofu or inflated TextFit deficits as layout
  defects;
- do not bypass the condition and claim authoritative visual PASS;
- author native text with the declared delivery family, record the font
  blocker and restrict local QA to geometry/object inventory until a CJK-capable
  PowerPoint render is available.

Do not trust a fontconfig family match by name. Inspect the resolved font
file's cmap and require actual Chinese glyph coverage. A readable manifest or
an existing Latin fallback file is not font evidence.

Bind the same task-local font directory to the final visual renderer. Artifact
Tool/Skia font registration proves authoring-side glyph availability only; it
does not make the family visible to LibreOffice. For LibreOffice closeout, run
`render_pptx.py --font-dir ...` and require the render receipt's
`fontconfig_bound=true` plus a non-empty `font_dir_sha256`. A blank-CJK render
is a renderer-font binding defect, not a layout-repair signal.

Do not use Unicode dingbats or emoji as production icons. Their glyphs and
metrics vary by platform. Use native-shape icon groups or independently
replaceable vector/raster assets with explicit provenance.

## Brand and decorative regions

Route every brand mark through native ImageGen as an independent final asset,
whether its reference is a screenshot or a separately supplied official
file. Use available brand files and screenshot crops as generation references
and geometry/color evidence; they do not bypass generation. Never trace a logo
with native shapes or silently reuse a screenshot crop as the final asset.
Compare the generated local crop against the reference, and keep the brand
picture independently movable with a stable `asset_id`, native ImageGen
receipt and post-export embedded-byte check.

Build decorative footer waves and skylines after content geometry. Use a small
number of semantic native shapes when they remain faithful; otherwise use one
independent decorative asset below native text.
If the source footer bleeds to the slide edge, add a matching native color
underlay across the final edge before placing a translucent decorative band.
Run `scripts/audit_continuous_band.py` with
`--require-bottom-edge-continuity` on the final render. Keep white footer
lettering above the band and verify its local crop for contrast and clipping.

## Efficient QA

The first candidate must emit an object inventory and one full-slide render.
Check in this order: canvas/aspect, large-region bounds, text presence, chart
topology, repeated-component alignment, brand/footer. Repair only the failing
region and re-render one adaptive crop plus the full slide once. Record object
counts by kind; a dense slide with zero native text or one full-frame image is
an immediate failure.

A direct composer result is a diagnostic candidate, not a delivery. Require a
bound reference route, full-page render, representative local crops and closed
material mismatches before release.
