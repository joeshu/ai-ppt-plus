# Dense single-slide reconstruction

Use this short loop for dense 16:9 dashboard, strategy-map and operating-model
slides whose reference combines a chart, repeated cards, management bands and
footer decoration.

## Fast decomposition

1. Freeze the source dimensions and author in one pixel coordinate space using
   `ref_width` and `ref_height`. Convert to slide units only in the authoring
   backend.
   If the request says standard PowerPoint 16:9, normalize the source geometry
   into `1280 x 720` authoring space and validate `12192000 x 6858000 EMU` at
   finalization. Do not carry a `1536 x 864` reference directly into the slide
   size, because that creates a non-standard `16 x 9 in` page.
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

Bind the same task-local font directory to the final visual renderer. Artifact
Tool/Skia font registration proves authoring-side glyph availability only; it
does not make the family visible to LibreOffice. For LibreOffice closeout, run
`render_pptx.py --font-dir ...` and require the render receipt's
`fontconfig_bound=true` plus a non-empty `font_dir_sha256`. A blank-CJK render
is a renderer-font binding defect, not a layout-repair signal.

Do not use Unicode dingbats or emoji as production icons. Their glyphs and
metrics vary by platform. Use native-shape icon groups or independently
replaceable vector/raster assets with explicit provenance.

Define one explicit icon slot inside every repeated component before fitting
adjacent text. Align icon slots by their visible alpha bounds and optical center,
not by the full transparent canvas. Keep equal rendered icon heights within a
semantic row; never let source padding decide apparent size or baseline.

Preserve numeric emphasis as a first-class text contract. Capture the source
number, unit, color and weight separately. If run-level styling does not survive
the target renderer, split the number and unit into adjacent native text boxes
with a shared baseline rather than losing the emphasis or rasterizing the pair.

For every prominent mixed-color title, subtitle and callout, inspect the first
fresh office render before accepting rich-text runs: some backends preserve the
text but discard per-run color. If the rendered color differs from the source,
split only at the style boundary into named native boxes. Measure the combined
phrase first, preserve visual word spacing, align the boxes to one baseline,
and bind each part to the same semantic parent. Re-render the whole phrase,
not just the emphasized fragment. Do not treat an authored run color or a
successfully extracted string as proof that the rendered emphasis survived.

For compressed five-column cards, reserve icon slots before text fitting and
derive icon size from the painted alpha bbox. Check apparent size and baseline
across siblings in the final office render. Keep one independent picture per
icon; batch sheets may be intermediate assets only and must obey the active
profile's maximum cell count. If a generated icon contains the wrong accent
color, repair or regenerate that asset before composition rather than relying
on the default image box to conceal the mismatch.

Treat a repeated column as a measured typography system, not just a shared
outer rectangle. Record for each role: visible font-height ratio, expected line
count, line spacing, inner padding and blank-space ratio. Allocate the densest
card first, then ordinary and compact cards. Use the same role measurements
across siblings, with component-local overrides only where the reference shows
different density. If `shrinkText` makes body copy visibly smaller than the
source or leaves disproportionate empty space, repair the text slot/card
geometry before accepting the smaller type.

Keep a one-line source column header on one line. Model the section number,
main title and qualifier as separately measured native slots with explicit
gaps; a narrow qualifier must not wrap under the main title merely because the
combined header text technically fits. Compare the final header baseline and
band height across all sibling columns.

Standard widescreen acceptance is based on the PPTX page size record. Require
`12192000 x 6858000 EMU`; do not fail or resize the deck because a renderer
rounds a 144-DPI preview to `1921 x 1080` instead of `1920 x 1080`.

For each icon row, record a visible-height ratio and optical-center offset
relative to its host/card. Match painted size across siblings, preserve any
source icon plate or soft host, and align row icons to the title/body anchor
observed in the source. Equal outer image boxes are insufficient evidence.

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

Batch semantically related ImageGen icons when the style is shared, then slice
them into independent final assets. Derive contrast-only variants from the
accepted alpha asset when no semantic pixels change. This reduces generation
round trips without collapsing editability or provenance.

A direct composer result is a diagnostic candidate, not a delivery. Require a
bound reference route, full-page render, representative local crops and closed
material mismatches before release.
