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

Define one explicit icon slot inside every repeated component before fitting
adjacent text. Align icon slots by their visible alpha bounds and optical center,
not by the full transparent canvas. Keep equal rendered icon heights within a
semantic row.

Capture emphasized numbers and their units separately. If run-level color or
weight does not survive the target renderer, use adjacent native text boxes on
one baseline rather than dropping the emphasis.

Inspect the first fresh office render of every mixed-color title, subtitle and
callout. If the exporter discards rich-run colors, split at style boundaries
into named native boxes with measured phrase widths and one shared baseline.
Preserve word spacing and re-render the complete phrase; authored run styling
alone is not color proof.

In dense five-column cards, reserve icon slots before text fitting. Size and
align each independent icon by its painted alpha bbox, not the transparent
canvas. A batch sheet is an intermediate only, and its cell count must respect
the active profile limit before invoking ImageGen. Check identity, foreground
color and apparent scale on the final slide, not just the isolated slices.

Model repeated columns as typography systems. Record expected line count,
visible font-height ratio, inner padding and blank-space ratio for header,
theme, card title, body and footer roles. Allocate the densest card first and
repair slot geometry before accepting smaller type from `shrinkText`.

Keep one-line source headers on one line by measuring section number, title and
qualifier in separate native slots with explicit gaps. Validate standard
widescreen from `12192000 x 6858000 EMU`; a one-pixel raster rounding at the
chosen preview DPI is not a page-size failure.

For repeated icons, compare painted height and optical center relative to the
host/card. Preserve visible source plates and align icons to the observed text
anchor; equal outer picture boxes alone do not establish alignment.

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
