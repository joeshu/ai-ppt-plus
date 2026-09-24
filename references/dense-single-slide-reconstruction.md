# Dense single-slide reconstruction

Use this short loop for dense 16:9 dashboard, strategy-map and operating-model
slides whose reference combines a chart, repeated cards, management bands and
footer decoration.

## Fast decomposition

1. Freeze the source dimensions and author in one pixel coordinate space using
   `ref_width` and `ref_height`. Convert to slide units only in the authoring
   backend.
2. Inventory large regions first: header/brand, status block, chart, repeated
   modules, guarantee band, results band and footer. Then assign stable IDs to
   their children. This prevents repeated OCR/layout passes.
3. Classify repeated icon-title-body modules as component groups, not tables.
   A visible grid is not table semantics.
4. Keep formal text in native text boxes. Keep cards, dividers, chart lines,
   markers, arrows and simple ribbons as native geometry. A full-slide raster
   is forbidden.

## Chart uncertainty

Use a native chart only when every category and value is verified. When a
reference image has missing, occluded, duplicated or contradictory labels,
author the visible trend as editable static line/marker primitives and record
`visual_transcription_unverified` in notes/evidence. Never invent authoritative
values to satisfy a native chart schema. Preserve visibly duplicated labels
until the user confirms a correction.

Run label-capacity preflight even when the values are verified. Dense native
chart engines may wrap five-digit values despite a correct workbook. When a
label cannot remain on one line at the reference size, disable automatic data
labels and author stable, editable native text labels at the verified point
anchors. Keep the underlying native chart and workbook editable, and validate
the separate label objects through the chart ledger and text-coverage audit.

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

Do not use Unicode dingbats or emoji as production icons. Their glyphs and
metrics vary by platform. Use native-shape icon groups or independently
replaceable vector/raster assets with explicit provenance.

## Brand and decorative regions

Generate every brand mark as an independent native ImageGen asset, using an
official standalone logo or screenshot crop as reference evidence when
available. A supplied official file does not bypass ImageGen for the final
asset. Never trace a logo with native shapes or silently insert a screenshot
crop as the final asset; retain the generated result as a movable, replaceable
picture and validate its local render crop against the reference.

Build decorative footer waves and skylines after content geometry. Use a small
number of semantic native shapes when they remain faithful; otherwise use one
independent decorative asset below native text.
Before placement, derive the painted band bbox after alpha-noise suppression,
then match that derivative to the physical slot aspect. A wide canvas with a
narrow painted center must not use `contain`, because it will visibly collapse
the footer; use a documented crop/cover transform or regenerate to the required
aspect.

## Efficient QA

The first candidate must emit an object inventory and one full-slide render.
Check in this order: canvas/aspect, large-region bounds, text presence, chart
topology, repeated-component alignment, brand/footer. Repair only the failing
region and re-render one adaptive crop plus the full slide once. Record object
counts by kind; a dense slide with zero native text or one full-frame image is
an immediate failure.

Budget repeated rows by content risk, not by uniform height. Classify each row
as compact, ordinary or dense from the source line topology, allocate the dense
row first, then distribute the remaining vertical space. This prevents a single
exception row from forcing a second full-layout pass.

For optional full-width decoration, place a native color underlay first so an
image decode failure cannot erase the contrast required by formal text.

A direct composer result is a diagnostic candidate, not a delivery. Require a
bound reference route, full-page render, representative local crops and closed
material mismatches before release.
