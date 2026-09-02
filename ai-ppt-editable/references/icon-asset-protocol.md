# Icon, decoration and word-art asset protocol

Apply this protocol to every reference-led page containing icons, badges,
decorations, logos, illustrations, or artistic typography. It adapts the
GordenImage2PPTX B4/B5 chain while preserving AI PPT Plus routing.

## B4: extract and exclude

Before PPTX engineering, inspect the reference and create a complete roster:
every icon, decoration, badge, logo, illustration, artistic word, and any item
that could be mistaken for a frame element. Separate ordinary editable text
from artistic typography. For every item record its role, semantic identity,
source-pixel bbox, whether it belongs to the frame, and whether it must be an
independent PPT object.

Then compare the original reference with the proposed frame preview. Record
both the full roster and the items accidentally included in the frame. No icon
may appear in both the frame and icon layers. If image generation is used,
record the actual generator/backend, prompt file, generated source, and copied
asset path. The image prompt must request only frame-excluded elements, and a
contact sheet must have evenly spaced cells with no intentional divider lines.
Small icons may use a 4x4 sheet only when the actual generated sheet has a
uniform 4x4 alpha layout. Do not infer that layout from the prompt: inspect
alpha row/column spans first. A variable-row sheet requires explicit row-aware
crops, and complex artistic typography must be cropped as one full visual line
per delivered asset, never as character tiles. A contact sheet is an
intermediate, never the delivered PPT object. See
`references/imagegen-sheet-slicing.md` for the required classification and
reject conditions.

Original icon files may be supplied as the authoritative source for a
deterministic `source_reuse` asset when the pixels are already complete and
only crop/alpha treatment is required. Missing, ambiguous or reconstructive
assets use the imagegen asset-sheet route. Both routes require source-vs-frame
evidence, B5 cutout/split QA where applicable, an independent delivered asset
and provenance hashes. A screenshot crop is not an original asset unless its
source bbox and source hash are recorded; a phone/viewer letterbox crop is
never a slide asset. If neither route can preserve fidelity, block the object
and request the source instead of inventing a substitute.

Complete brand lockups are an exception to grid splitting: keep the logo mark
and wordmark together as one `brand_lockup`/`role: logo` asset. Do not pass a
complete lockup to `slice_grid.py --auto`, because automatic segmentation can
split the mark from its wordmark. Alpha-trim or crop the generated lockup
output without splitting it, and record `whole_asset_contract` in the object
manifest. Only independently replaceable non-brand icons may be split into
separate delivered assets.

## Imagegen extraction evidence gate

For every icon, decoration and artistic word, first select and record one
provenance mode. In `imagegen` mode, use the ChatGPT imagegen skill (or an
explicitly declared image-generation backend) to create an isolated,
frame-excluded icon/decorative asset sheet. The prompt must use the current
reference as the edit target and request no ordinary text, frame, card, or
background. Do not use code to draw or reconstruct a missing asset. In
`source_reuse` mode, copy/crop the authoritative source deterministically and
record its source bbox/hash; this is the fast path for exact supplied assets
and does not need a redundant generation call.

Before composition, every page must contain `imagegen-assets-manifest.json`,
which is the backwards-compatible visual-asset provenance manifest. For
`provenance_mode: imagegen`, record non-empty `generated_source`, `copied_to`,
`layer`, `prompt_file`, `backend`, and `key_color`. For
`provenance_mode: source_reuse`, record `source_ref`, `source_bbox`,
`source_sha256`, `copied_to`, `layer`, and `extraction_method`. Copied assets
remain inside the unique RUN_ROOT and must pass current SHA-256 validation.
Missing provenance or a stale hash blocks conversion. Run
`scripts/validate_imagegen_assets_manifest.py imagegen-assets-manifest.json`
before B5; the validator accepts both modes and reports which one was used.

This evidence gate is separate from the visual route: reference reconstruction does not generate a new whole-slide visual intermediate, but it may generate an isolated missing icon sheet under this rule. A generated icon sheet is still only an intermediate; after copying it into RUN_ROOT it must pass B5 chroma-key, split, contact-sheet, edge and placement review.

## B5: cut out, split and inspect

For generated or supplied assets on a flat background, use the portable tools:

```bash
python3 scripts/probe_palette.py reference/slide-1.png --output qa/palette-report.json
python3 scripts/chroma_key.py --input icons_raw.png --out icons_transparent.png --preset icon-safe --scale 2 --force
python3 scripts/slice_grid.py icons_transparent.png assets/icons --auto --pad 24 --contact-sheet --prefix ic
python3 scripts/placement_qa.py reference/slide-1.png slide-manifest.json --out-dir qa/icon-placement
python3 scripts/validate_icon_assets.py icon-asset-manifest.json --report reports/icon-assets.json
python3 scripts/audit_icon_layers.py icon-asset-manifest.json --report reports/icon-layers.json
```

Use `frame-safe` for a frame layer and `icon-safe` for icons, decoration,
and artistic typography. Preserve RGB colors, thin strokes, glows and
anti-aliased alpha; do not use aggressive despill/erosion that changes brand
colors or breaks lines. Split only after transparency is valid. Use automatic
transparent-gap segmentation for imperfect AI sheets; use component slicing
for frame parts only when the user explicitly requests movable frame parts.
Inspect the contact sheet and a frame preview on a neutral/gray background.

Generated neon green or magenta backgrounds can contaminate anti-aliased
edges. If the composite shows black, green, or magenta fringes, retry with an
explicit key color and conservative hard-key settings such as
`--no-despill --no-edge-recover`, then composite the result over the generated
background before accepting it. A successful command exit is not visual proof.

Every item must pass: non-empty alpha, valid visible bbox, no unaccepted
edge-touch/truncation, no residual key color or grid line, no unintended
connected-component merge, no duplicate frame/icon occurrence, and correct
source-pixel coordinate mapping. A failed machine check blocks the page;
rendered visual review remains mandatory.

## Manifest and editability

The page must have an `icon-asset-manifest.json` with schema
`ai-ppt-plus/icon-assets/v1`, complete B4/B5 evidence, and one record per
independent icon/decorative asset. Each record includes `asset_id`, `role`,
`source_ref`, `source_bbox`, `extraction_method`, `frame_exclusion`,
`asset_path`, `sha256`, `editability_level`, `replaceable`, `alpha_quality`,
`edge_touch`, `split_status`, `duplicate_guard`, `anchor`, and
`review_status`. The top level also records `source_vs_frame_review`,
`frame_asset_ids`, `icon_asset_ids`, `frame_preview`, and
`contact_sheet`.

`sha256` is the hash of the delivered file at `asset_path`, not the hash of
the source screenshot. Run `scripts/validate_icon_assets.py --require-hashes`
and the project-wide `scripts/validate_asset_hashes.py` before strict release.

Use independent PPT picture objects for extracted icons and decoration unless a
genuinely editable vector/native equivalent is selected. Extracted icons and
artistic typography are L2; native vectors are L1; missing assets are L4;
unverifiable assets are L5; a whole-slide bitmap is L0. Review icon count,
identity, color, stroke weight, size, center, spacing, layering, crop, and text
collisions. Record every correction and its reason.
