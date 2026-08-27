# Icon, decoration and word-art asset protocol

Read this protocol for every reference-led page containing icons, badges,
decorative marks, illustrations, logos, or decorative typography. It adapts
the B4/B5 extraction and cutout discipline to AI PPT Plus without making
image-generation mandatory for `reference-reconstruction`: a supplied source
asset, an approved generated result, or a reliable native/vector replacement
may be used, but its origin and treatment must be recorded.

## B4 — inventory and extract

Before engineering the page, create an asset roster from the reference:

- list every icon, decoration, badge, logo, illustration and decorative word;
- distinguish ordinary editable text from decorative/artistic typography;
- mark whether each item belongs to the frame/background or is an independent
  movable object;
- compare the roster with the frame layer and record anything accidentally
  included in both layers;
- prefer one independently replaceable asset per visible object; use a contact
  sheet only as an intermediate, never as the delivered PPT object;
- preserve brand marks and specialized artwork exactly when supplied; do not
  invent a low-quality substitute.

Record `asset_id`, `role`, `source_ref`, `source_bbox` in source pixels,
`extraction_method`, `frame_exclusion`, `editability_level`, and the planned
PPT object path for every item. `decorative_word_art` belongs to the visual
asset layer and must not be silently converted into formal text.

## B5 — cut out, split and inspect

When an asset is delivered on a background, remove only the background using a
chroma-safe or alpha-preserving method. Preserve source colors, thin lines,
glows and anti-aliased edges; do not use aggressive color decontamination that
changes brand colors or erodes small strokes. Split a contact sheet by
transparency/connected gaps only after background removal. Never crop icons
directly out of the original slide screenshot as a shortcut.

Every extracted object must pass: non-empty alpha and a valid visible bbox;
no accidental `edge_touch` or truncation unless explicitly accepted; no
unintended connected-component merge or residual grid/divider line; no
duplicate object in frame and icon layers; source-pixel bbox mapped to the
slide coordinate system; and intentional transparent padding that preserves
the visual anchor. Run `scripts/validate_icon_assets.py`; a failure blocks the
affected page. The validator is diagnostic, so rendered visual review remains
mandatory.

## Placement and editability

Place extracted icons/decorations as independent PPT picture objects unless a
reliable editable vector/native equivalent is explicitly chosen. Link
`source_bbox`, `x/y/w/h`, `anchor`, and `asset_id` in the slide manifest. Use
`L2` for a movable/replaceable extracted image and disclose that its pixels are
not internally editable. Use `L1` only for a genuinely editable vector/native
equivalent. Use `L4` for an accurate missing-asset placeholder; use `L5` when
the visual identity or content cannot be verified. A whole-slide bitmap is
`L0` and never an icon solution.

Rendered review must check icon count, semantic identity, color, stroke weight,
size, center point, spacing, layering, crop, and text collisions. Fix placement
using the source bbox center as anchor; do not shrink or delete an icon merely
to avoid a collision. Record corrections and reasons.

Minimal manifest shape:

```json
{
  "schema": "ai-ppt-plus/icon-assets/v1",
  "slide_no": 1,
  "assets": [{
    "asset_id": "S01-icon-03", "role": "icon",
    "source_ref": "user-reference#icon-03",
    "source_bbox": {"x": 1250, "y": 210, "w": 48, "h": 48},
    "extraction_method": "approved-source-asset",
    "cutout_method": "none",
    "prompt_ref": null,
    "frame_exclusion": "verified-not-in-frame",
    "asset_path": "assets/icons/icon-03.png",
    "editability_level": "L2", "replaceable": true,
    "alpha_quality": "pass", "edge_touch": false,
    "split_status": "single-object", "duplicate_guard": "pass",
    "anchor": "center", "review_status": "pending"
  }]
}
```
