# Chart reconstruction protocol

Charts in a reference image have two different authorities:

- the reference image owns the visible geometry, typography, colors, labels,
  gridlines and reading order;
- a workbook, CSV, approved outline or user confirmation owns the numeric data.

Never promote pixels into authoritative data silently. A chart may be visually
recoverable while its numbers remain unverified.

## Representation decision

Use the least lossy representation that the evidence supports.

| Representation | Use when | Visible construction | Editability declaration |
|---|---|---|---|
| `native_chart` | Every value is authoritative and traceable | Native chart with verified categories/series; manual text overlays are allowed | `L1`; chart data must match cache and embedded workbook |
| `static_line_primitives` | The line geometry can be transcribed but the data is not authoritative, or native chart styling is not stable enough | Native lines/markers plus independent text, legend and gridline shapes | Native movable primitives; not a claim that the chart has an authoritative workbook |
| `svg` | A verified vector chart is supplied and its source is preserved | Independent SVG asset plus native formal text | `L2` unless internal path editability is proven |
| `raster_fallback` | Point values or geometry cannot be recovered reliably | Exact verified chart crop, with surrounding formal text kept native when possible | Explicit `L3` degradation and reason required |

For small, dense Chinese charts, the default rendering strategy is hybrid:
native lines/markers or primitives, independent text boxes for data labels,
months, units and legends, and a separate panel substrate for gradients and
borders. Do not use automatic PowerPoint data-label placement as the visual
authority; WPS, PowerPoint and LibreOffice place those labels differently.

## Data states

`source_data_status` has one of three meanings:

- `verified`: supplied by an authoritative table or explicitly confirmed by
  the user; eligible for `native_chart`.
- `unverified`: a visual/OCR transcription is available, but the original data
  has not been confirmed; eligible for `static_line_primitives`, not for a
  native authoritative chart.
- `unavailable`: the value or geometry cannot be recovered sufficiently; use a
  documented raster fallback or stop the affected chart.

Missing months are represented as `null`, never as zero. When a series has
missing values, declare `missing_value_policy: blank_not_zero` and preserve the
visible end of the series. This is especially important for a current-year
series that stops at July.

## Required chart record

Create `chart-reconstruction.json` independently of the final PPTX. Each chart
record contains:

- `chart_id`, `slide_no`, title and `representation`;
- `source_data_status`, `data_source` and `data_snapshot_sha256`;
- exact `categories` and series values, allowing `null` for missing values;
- `required_elements` and `visible_elements` for title, legend, months, units
  and data labels;
- reference and plot geometry in a declared coordinate space;
- style tokens for series colors, line width, marker and gridlines;
- a region QA record and any explicit degradation reason.

Run `scripts/validate_chart_manifest.py` before composition. The validator
rejects unverified native charts, inconsistent series lengths, non-finite
values, accidental zero-filling, missing visible annotations and stale data
hashes.

## Page execution

1. Crop only the chart regions at source resolution. Keep the raw reference and
   its SHA-256; viewer letterboxing is not chart content.
2. Inventory plot box, title, units, months, gridlines, series, markers,
   legend, label colors and label offsets.
3. Build and reconcile the canonical data matrix. OCR is an input to review,
   not authority. Compare every label with its point location and trend.
4. Select the representation using the decision table. For the hybrid route,
   keep the panel substrate separate and place text overlays above it.
5. Render only the affected chart regions during repair. Compare each chart
   crop, then perform one full-slide render before release.
6. Run semantic QA: categories, series, nulls, units, visible annotations,
   data hash, object type and source hash must agree. Human review remains
   mandatory for small labels and ambiguous values.

## Current reference-image pilot

For the China Unicom page, the three upper charts have dense labels and no
authoritative workbook. The recommended target route is static/vector lines
with native labels for all three. In the current staged repair, chart 2 is the
first completed hybrid pilot; chart 1 and chart 3 remain explicit
`raster_fallback` routes until their line geometry is repaired. All three are
unverified visual transcriptions, and the 2026 series is blank after July.

After a user-approved data table is supplied, the same chart records can be
promoted to `native_chart` only after the value hash and rendered point
geometry both pass QA. Do not change the visual layout merely to make a native
chart easier to author.

## Performance rules

Do not call image generation for precise line charts. Run OCR and visual
inspection on three chart crops in parallel, cache the canonical data/style
records by source hash, and use `--affected-pages` plus `--affected-region` for
repair iterations. Run expensive full-deck rendering and release aggregation
once after all chart changes are batched.
