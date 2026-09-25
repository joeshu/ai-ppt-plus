# Image-to-Editable Regression Rules

Use this reference for fixed-reference image-to-editable replays after the
first fresh render exposes a fidelity defect. These rules turn recurring
repairs into reusable preflight and closeout behavior; they do not create a
universal pixel-score threshold.

## 1. Inventory all salient visuals, including embedded marks

The source-visual inventory must include every visually material complex
visual, not only standalone icons and logos. Include embedded footer/header
calligraphy, decorative brush marks, skyline/ribbon systems, seals, wordmarks
and complex card art as separate `visual_id` records with a semantic role,
source bbox, `required_route`, `asset_id` and final placement binding.

Re-run the upstream-to-final coverage gate after every inventory change. A
render can look plausible while still being incomplete if a salient source
mark is absent from the inventory. Missing inventory coverage is a provenance
failure, not a reason to silently crop the source image.

## 2. Treat alpha noise and full-bleed geometry as different contracts

For bounded icons, brands and pictograms, keep the existing transparent-asset
thresholds unchanged: real RGBA alpha, safe padding, transparent corners,
alpha-visible bbox and visual-centroid evidence are required.

For an explicitly full-bleed ribbon, skyline or wave, tiny antialiasing alpha
noise can make the raw alpha bbox much larger than the painted band. Create a
named derived asset using a documented alpha-noise trim/edge anchoring step,
preserve the raw ImageGen asset, record the threshold and transform in
placement evidence, and set `allow_bleed: true` only for that semantic slot.
Do not reuse the exception for bounded assets and do not lower their QA
thresholds.

Fit a full-bleed derivative to the target physical aspect ratio before placing
it. Prefer `contain` when the derivative already has the target aspect; use
`cover` only with an explicit crop/contour record. A `cover` fit with an
unmatched aspect ratio is a crop risk even when the object exists and alpha QA
passes.

## 3. Resolve normalized geometry in physical slide space

Normalized coordinates are not isotropic on a 16:9 slide. A native object that
is intended to be circular must carry a physical-aspect intent: compare
`w * slide_width_px` with `h * slide_height_px`, then compensate the normalized
bbox or use a true ellipse with the measured physical diameter. Apply this to
number badges, icon plates, KPI roundels and circular card hosts.

Do not close a visual repair because the normalized numbers look symmetric.
Verify the rendered crop; a mathematically square normalized box can render as
an obvious oval, and a circular source plate can lose its color identity if
all repeated hosts reuse one fill.

## 4. Bind formal text to its semantic container

Every summary, label, callout or footer slogan must be bound to the strip,
card, badge or parent visual system that carries it. Record the parent or
anchor relationship in the AuthoringPlan and keep the text bbox inside the
intended carrier geometry. A TextFit pass only proves that text fits its own
box; it does not prove that the text is inside the correct strip.

When mixed-color rich text is unavailable, split the visual into native
editable parts: a native colored bullet/check/number shape and a native text
box for the black body copy. Preserve the observed line topology and audit
the composed crop, not just the text box.

Do not use a font glyph as the final bullet when the reference depends on its
shape, color or exact alignment. Renderers can substitute the glyph, change its
advance width or lose its color. Use a small named native shape and position it
against the paragraph's first rendered line. For wrapped paragraphs, store one
bullet anchor per paragraph rather than spacing bullets by a constant line step.

Resolve icon color from the parent fill before asset placement. Dark or saturated
title bands require an approved high-contrast variant, commonly a white derivative
of the accepted ImageGen alpha asset. Do not reuse a red-on-transparent icon on a
red band merely because the semantic icon matches.

Optional decorative imagery must not be the only carrier of contrast for formal
text. Add a native color underlay before the decoration, then render-test the deck
with the actual office renderer. If the decoration fails to decode, the title and
brand fields must remain legible and structurally complete.

Treat every colored number, percentage, rank and unit relationship as an
explicit run contract. Compare the rendered result, not only the authoring model.
If mixed-run color or size is lost on export, split the number and unit into named
native text boxes, preserve their shared baseline and keep the semantic group
independently editable.

Reserve icon geometry before text fitting. For generated transparent icons,
measure the visible alpha bbox, normalize optical center and scale by painted
height. A row of equal outer image boxes can still look misaligned when the
generated assets have different transparent padding.

## 5. Close out by region and by responsibility

The final visual closeout must inspect, at minimum, top brand/title, the full
header/title block, each repeated column/card system, salient icon clusters,
right-side prompt cards and the composed footer band. Include same-coordinate
reference/candidate crops for relationships that cannot be judged from an
object-only thumbnail.

Use stable repair codes when recording defects so future runs can aggregate
them:

- `VIS-SOURCE-VISUAL-INVENTORY-MISSING` — salient source art has no final
  independent asset binding.
- `VIS-ALPHA-NOISE-CANVAS` — alpha noise or transparent padding changes the
  visible full-bleed band geometry.
- `VIS-FULLBLEED-COVER-CROP` — a full-bleed asset is cropped by an unmatched
  physical aspect ratio.
- `VIS-NATIVE-GEOMETRY-ASPECT` — a circle/roundel/badge is visibly stretched.
- `VIS-TEXT-CONTAINER-DETACHED` — formal text fits but is detached from its
  intended strip/card/parent system.
- `VIS-CARD-COLOR-IDENTITY` — repeated card hosts lose source color roles.
- `VIS-COMPOSITE-ANCHOR-DRIFT` — footer/header child anchors drift after the
  parent band or contour changes.

Technical evidence readiness is not visual PASS. Keep the run pending until
the human crop closeout is explicitly passed; if any required evidence is
missing, report `NOT_RUN`, and if a formal gate fails, report `FAIL`.

## 6. Bind embedded assets by bytes, not by authoring-path lifetime

For a final ImageGen asset, pass the decoded image bytes plus content type to
the authoring backend. A local path is acceptable only when the export receipt
proves that the backend embedded the bytes before the temporary path can move
or disappear. A gray placeholder in either the authoring preview or the fresh
PPTX render is an asset-binding failure, even when the source PNG exists.

Hash the exact bytes passed to the backend and require the same hash in the
post-export media audit. Cache the decoded bytes once per accepted asset and
reuse them across candidate rebuilds; do not re-read or regenerate unchanged
assets during text/geometry-only repair rounds.

## 7. Preflight dense native chart labels

Before authoring a dense native chart, compare each displayed label's measured
width with its available horizontal slot. If a verified five-digit value would
wrap or split in the native chart data-label engine, keep the chart and workbook
native but turn off automatic data labels and place separately named native
text labels at the verified point anchors. Bind each label to the chart ledger
and text-coverage evidence. Never accept a wrapped `18345` as `183` plus `45`.

Use these additional stable repair codes:

- `VIS-ASSET-PATH-NOT-EMBEDDED` — an asset path existed but the exported PPTX
  contains a placeholder or mismatched media bytes.
- `VIS-CHART-LABEL-WRAP` — a verified chart label wraps, splits or collides in
  the fresh render.
