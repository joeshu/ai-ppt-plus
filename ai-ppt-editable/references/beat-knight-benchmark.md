# Beat-Knight competitive benchmark

## Purpose

Knight is the external competitive baseline for image-to-editable-PPTX reconstruction. A candidate is not considered better because it contains more machinery or passes internal unit tests. It must beat the frozen Knight result on the same source image under a five-dimensional evaluation while preserving native editability.

Frozen upstream reference for this benchmark: `knight6669/knight-imagetopptx-skill@9265818222fdbdd326410793956ad23a950d72a7`.

## Required dimensions

For each benchmark page record both Knight and candidate results:

1. `pixel` — full-page normalized render similarity. Report blurred-layout SSIM plus a foreground-weighted pixel score. The candidate must not hide text or objects in a full-slide raster.
2. `text` — transcription equality, missing/extra text, line-count preservation, overflow, font family/size/weight/color evidence, and text-slot geometry. All formal text must remain native editable text/runs.
3. `object` — semantic object coverage, source-bbox geometry error, z-order, grouping and editability. Repeated components must not be collapsed into tables or screenshots.
4. `icon_asset` — per-icon visible alpha bbox IoU, visual-centroid error, scale error, color-role error, clipping/padding, and independent movability. Contact/sprite sheets are never final assets.
5. `local_crop` — same-coordinate hard-region comparison for dense cards, icon slots, compact arrows, table/list boundaries and user-flagged regions. Report the worst crop, not only the mean.

## Win condition

A benchmark case is a `candidate_win` only when all of the following are true:

- candidate visual gate remains >= 0.90;
- candidate has zero flattened formal-text pages and zero whole-page screenshot substitutions;
- candidate has no new blocking text overflow, object drift, icon clipping, matte/background contamination or semantic table/list misclassification;
- candidate is no worse than Knight in every required dimension within the metric tolerance;
- candidate is strictly better than Knight in at least three of the five dimensions;
- `pixel` or `local_crop` must be one of the strictly better dimensions;
- every claimed improvement is backed by saved evidence and replayable source/candidate coordinates.

A suite-level `beat_knight=true` requires wins on every mandatory benchmark case. Do not average away a losing page. If a case ties, report a tie; if it loses, keep the branch unmerged and repair the responsible layer.

## Repair priority

When the candidate loses, repair in this order unless evidence points elsewhere:

1. source geometry / PageGraph lock;
2. text-slot geometry and full-slot TextFit;
3. alpha-visible bbox / visual-centroid placement;
4. asset color/shape/transparent-padding fidelity;
5. arrow/connector path geometry and z-order;
6. typography compensation local to the failing object;
7. final local crop repair.

Never lower the 0.90 visual gate, rasterize formal text, replace independent assets with a page crop, or remove objects to improve the score.

## Evidence bundle

Each run must retain:

- source image/hash and physical slide size;
- Knight PPTX/render and candidate PPTX/render;
- text/object/icon manifests;
- full text-fit coverage report;
- transparent asset QA and alpha-centroid placement report;
- same-coordinate crop roster and crop images;
- per-dimension JSON metrics;
- a compact `beat-knight-report.json` containing raw Knight score, raw candidate score, delta, pass/fail reason and the final `beat_knight` decision.

The standard widescreen physical target remains `13.333333 x 7.5 in` unless the source explicitly requires another aspect ratio.