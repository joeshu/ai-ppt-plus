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

Supplied original icon files may be used directly when their provenance is
known. A screenshot crop is not an original asset: do not silently promote a
crop to a high-fidelity extracted asset. If no reliable source asset exists,
use the approved image-generation extraction route or mark an accurate L4
placeholder; do not invent a weak branded or complex replacement.

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
