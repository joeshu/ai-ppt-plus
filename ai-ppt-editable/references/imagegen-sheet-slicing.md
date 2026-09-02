# Imagegen sheet slicing contract

This B4/B5 adapter prevents a plausible imagegen prompt from becoming an
incorrect sprite sheet because the workflow assumed a grid the model did not
produce.

## Classify before slicing

Read the alpha channel of the chroma-keyed sheet and record occupied row and
column spans. Classify it as:

- `uniform_grid`: every row has the same object count and comparable spacing;
  fixed-grid slicing is allowed only with recorded dimensions.
- `variable_row`: row counts or cell widths differ; use row-aware explicit
  crops or transparent-gap segmentation and map every crop to the roster.
- `artistic_row`: calligraphy, brush lettering, glow text or a large decorative
  word spans multiple characters; deliver one full visual line per asset, not
  character tiles.

The manifest records `sheet_class`, `slice_mode`, `row_spans`,
`column_spans`, and expected roster count. A `4x4` command without
`uniform_grid` evidence is a blocking error.

## Crop and inspect

After cropping, verify every asset has a non-empty alpha bbox, no unintended
neighbor, no clipped stroke or glyph, no residual key color, and no unsafe
edge-touch. For artistic rows, verify the complete line and internal spacing
are preserved.

The contact sheet is QA evidence, never a delivered object. It must show the
expected count and complete independent objects on a neutral background. Chopped
art, missing tails, merged objects, or a count mismatch blocks composition.

## Font preflight coupling

Run the font probe before composition. The declared family, file format and
sha256 in the font manifest must match the actual file used for rendering or
embedding. A stale font alias or invalid font package blocks the run; choose a
validated variant and re-run render plus embedding. Do not silently continue
with a fallback that makes Chinese text disappear.

## Required evidence

Preserve the raw generated path, chroma-keyed path, contact sheet, crop
manifest and final independent object IDs. Row-aware and full-row crops are
derived crops of an imagegen asset, not `source_reuse`. The final manifest must
pass strict imagegen validation and the rendered slide must be compared with
the frozen reference.
