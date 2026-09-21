# Icon, decoration and word-art asset protocol

Apply this protocol to every reference-led page containing icons, badges,
decorations, logos, illustrations, or artistic typography. It defines the
native AI PPT Plus B4/B5 asset-isolation chain.

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

An individual alpha-trimmed cell derived from a generated sheet may be a
delivered independent asset. Record `derived_from_sheet: true`, a non-empty
`derived_transform` with the source-sheet bbox and slice mode, the delivered
file hash, `independent_asset: true`, and `contact_sheet: false`. The final
`copied_to` path must name the individual asset, never the sheet or contact
sheet. Validators must reject sheet delivery but accept this explicit
source-sheet-to-independent-slice contract.

Original non-brand files may be supplied as authoritative source evidence for a
deterministic `source_reuse` fallback only when the user explicitly requests
the exact supplied pixels or explicitly approves the fallback after ImageGen
failure. Missing, ambiguous or reconstructive assets use the ImageGen route.
Both routes require source-vs-frame evidence, B5 cutout/split QA where
applicable, an independent delivered asset and provenance hashes. A screenshot
crop is not an original asset unless its source bbox and source hash are
recorded; a phone/viewer letterbox crop is never a slide asset.

Brand visuals never use this fallback. Logos, wordmarks, calligraphic slogans,
brand bands, 5G marks and other brand-class assets must be generated natively
by ImageGen as independent assets. Their source crops are reference evidence
only.

Complete brand lockups remain one generated `brand_lockup`/`role: logo` asset.
Do not pass a complete lockup to `slice_grid.py --auto`, because automatic
segmentation can split the mark from its wordmark. Validate the generated
transparent asset as a whole and record `whole_asset_contract` in the object
manifest. This is a whole-asset generation rule, not a source-reuse exception.

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
`layer`, `prompt_file`, `backend`, and `background_mode`. Record `key_color`
only when `background_mode` is a chroma-key mode. Also record
`fallback_level`, `canonical_asset`, `qa_preview_only`, and a cache key derived
from the reference SHA, source bboxes, normalized prompt, backend, and style
lock. At the manifest top level, record billable generation/edit calls
separately from local derivatives and QA previews. For
`provenance_mode: source_reuse`, record `source_ref`, `source_bbox`,
`source_sha256`, `copied_to`, `layer`, and `extraction_method`. Copied assets
remain inside the unique RUN_ROOT and must pass current SHA-256 validation.
Missing provenance or a stale hash blocks conversion. Run
`scripts/validate_imagegen_assets_manifest.py imagegen-assets-manifest.json`
before B5; the validator accepts both modes and reports which one was used.

This evidence gate is separate from the visual route: reference reconstruction
does not generate a new whole-slide visual intermediate, but it may generate an
isolated missing icon sheet under this rule. A generated icon sheet is still
only an intermediate. After copying it into RUN_ROOT, validate direct alpha
first. If alpha passes, skip chroma keying and continue with split,
contact-sheet, edge and placement review. Chroma keying is a last fallback, not
a mandatory B5 step.

## B5: cut out, split and inspect

Request genuine transparent PNG output first. Validate it at the deterministic
handoff boundary and use `slice_grid.py` directly when the alpha channel is
meaningful. For assets that reached the final chroma-key fallback, use the
portable tools:

```bash
python3 scripts/probe_palette.py reference/slide-1.png --output qa/palette-report.json
python3 scripts/chroma_key.py --input icons_raw.png --out icons_transparent.png --preset icon-safe --scale 2 --force
python3 scripts/slice_grid.py icons_transparent.png assets/icons --auto --pad 24 --contact-sheet --prefix ic
python3 scripts/placement_qa.py reference/slide-1.png slide-manifest.json --out-dir qa/icon-placement
python3 scripts/validate_icon_assets.py icon-asset-manifest.json --report reports/icon-assets.json
python3 scripts/audit_icon_layers.py icon-asset-manifest.json --report reports/icon-layers.json
```

Do not generate red, white, gray, green and transparent variants to compare
backgrounds. Direct-alpha is attempt one; edit-to-transparent is attempt two;
one selected chroma color is the final fallback. Red/gray/white composites are
allowed only as locally derived QA previews and should be consolidated into one
contact sheet marked `qa_preview_only`.

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

For a multi-icon sheet, preserve every accepted cell. Regenerate or edit only
the failed cell, then rerun split/placement QA for that cell and the assembled
contact sheet. Never regenerate the complete sheet because one cell failed.

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
`review_status`. Imagegen records additionally include `background_mode`,
`fallback_level`, `canonical_asset`, `qa_preview_only`, and `cache_key`. The top
level also records `source_vs_frame_review`,
`frame_asset_ids`, `icon_asset_ids`, `frame_preview`, and
`contact_sheet`, plus `generation_accounting` with billable generation calls,
billable transparent-edit calls, local derivative count, QA preview count,
full-sheet retries, and single-asset retries.

`sha256` is the hash of the delivered file at `asset_path`, not the hash of
the source screenshot. Run `scripts/validate_icon_assets.py --require-hashes`
and the project-wide `scripts/validate_asset_hashes.py` before strict release.

Use independent PPT picture objects for extracted icons and decoration unless a
genuinely editable vector/native equivalent is selected. Extracted icons and
artistic typography are L2; native vectors are L1; missing assets are L4;
unverifiable assets are L5; a whole-slide bitmap is L0. Review icon count,
identity, color, stroke weight, size, center, spacing, layering, crop, and text
collisions. Record every correction and its reason.
