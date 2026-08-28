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
Small icons may use a 4x4 sheet; larger decoration, objects, or artistic
typography should use a 2x2 sheet or a separate sheet. A contact sheet is an
intermediate, never the delivered PPT object.

Original icon files may be supplied as the imagegen edit target/reference, but may not be copied directly into the delivered icon layer. Every icon, decoration and artistic word must pass the same imagegen asset-sheet route, followed by B5 cutout, split and QA. A screenshot crop is never an original asset and may not bypass imagegen. If imagegen is unavailable or fails, block the page; do not silently fall back to direct crops, weak redraws or unproven substitutes.

## Imagegen extraction evidence gate

For every icon, decoration and artistic word, use the ChatGPT imagegen skill (or an explicitly declared image-generation backend) to create an isolated, frame-excluded icon/decorative asset sheet. The prompt must use the current reference as the edit target and request no ordinary text, frame, card, or background. Do not use code to draw or reconstruct the icon sheet, and do not crop a local screenshot region as a substitute.

Before composition, every page must contain `imagegen-assets-manifest.json`. For `background`, `frame_raw`, and every `icons_raw_*` layer, record non-empty `generated_source`, `copied_to`, `layer`, `prompt_file`, `backend`, and `key_color`. `backend` must be imagegen-class; `copied_to` and `prompt_file` must resolve inside the unique RUN_ROOT. Missing manifest or missing evidence for any image layer blocks conversion. Run `scripts/validate_imagegen_assets_manifest.py imagegen-assets-manifest.json` before B5.

This evidence gate is separate from the visual route: reference reconstruction does not generate a new whole-slide visual intermediate, but it may generate an isolated missing icon sheet under this rule. A generated icon sheet is still only an intermediate; after copying it into RUN_ROOT it must pass B5 chroma-key, split, contact-sheet, edge and placement review.

## B5: cut out, split and inspect

For generated or supplied assets on a flat background, use the portable tools:

```bash
python3 scripts/probe_palette.py reference/slide-1.png
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
`asset_path`, `editability_level`, `replaceable`, `alpha_quality`,
`edge_touch`, `split_status`, `duplicate_guard`, `anchor`, and
`review_status`. The top level also records `source_vs_frame_review`,
`frame_asset_ids`, `icon_asset_ids`, `frame_preview`, and
`contact_sheet`.

Use independent PPT picture objects for extracted icons and decoration unless a
genuinely editable vector/native equivalent is selected. Extracted icons and
artistic typography are L2; native vectors are L1; missing assets are L4;
unverifiable assets are L5; a whole-slide bitmap is L0. Review icon count,
identity, color, stroke weight, size, center, spacing, layering, crop, and text
collisions. Record every correction and its reason.