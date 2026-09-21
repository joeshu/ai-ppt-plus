# Native ImageGen asset runbook

Use this runbook for every fixed-reference image-to-editable-PPTX task that
contains icons, logos, calligraphy, illustrations, photos, textures, gradients,
ribbons, skyline bands or other non-native visual assets.

## Route

1. Freeze the reference path, dimensions and SHA-256.
2. Inventory every visible non-text visual and assign an `asset_id` and source
   bbox. Do not inventory only the easiest icons; include brand marks,
   calligraphy, footer art and background decoration.
3. Keep formal text, numbers, ordinary cards, dividers and simple reliable
   geometry native. Route every other visual to `imagegen_asset`.
4. Call the built-in native ImageGen tool `image_gen.imagegen` for each
   independent asset. Use the reference only as visual guidance; never use a
   source crop as the delivered asset. Generate transparent RGBA for overlays.
5. Record the prompt, source reference, generated output and native-tool
   receipt before composing the PPTX. Missing receipt means `blocked`; do not
   fabricate a backend name or continue with a scripted icon.

Brand lockups, calligraphy, wide bands and complex art always use dedicated
ImageGen calls. Compatible simple alpha icons may use an explicitly declared
batch to reduce latency, but the batch is an intermediate only: every cell must
be sliced into an independent final asset and receive its own alpha, identity,
color, placement and local-crop QA record. Set
`independent_generation_per_asset: true` when the user explicitly requires one
native generation transaction per visual asset.

## Required manifest evidence

Set these fields at the manifest root for new fixed-reference runs:

```json
{
  "provenance_policy": "imagegen_final_assets",
  "native_tool": "image_gen.imagegen",
  "native_tool_receipt_required": true
}
```

Each `provenance_mode: imagegen` asset must additionally include:

```json
{
  "generated_source": "assets/generated/icon.png",
  "copied_to": "assets/editable/icon.png",
  "prompt_file": "assets/prompts/icon.txt",
  "backend": "native-imagegen",
  "native_imagegen_receipt": {
    "tool": "image_gen.imagegen",
    "mode": "new",
    "source_reference": "references/source.png",
    "prompt_sha256": "<64 lowercase hex characters>",
    "output_path": "assets/generated/icon.png",
    "generation_request_id": "<stable request or batch id>",
    "recorded_at": "2026-09-21T00:00:00Z"
  }
}
```

The receipt is provenance evidence, not permission to skip visual QA. Validate
the manifest before composition and after the final render:

```bash
python3 scripts/validate_imagegen_final_assets.py \
  imagegen-assets-manifest.json --strict \
  --report qa/imagegen-final-assets.json
```

The strict validator must reject a missing receipt, a non-native tool name, a
missing prompt/output file, a source crop, a missing delivered hash or a final
asset that is not independently movable.

## Alpha and placement

Validate genuine RGBA alpha, non-empty visible bbox, transparent corners,
safe padding, clipping and visible-alpha centroid. For full-bleed bands, keep
the raw generated file, derive a documented alpha-trimmed/cropped derivative,
and compare its contour in the final slide region. Use `contain` for bounded
icons and `cover` or a documented physical-aspect crop for continuous bands;
do not let transparent padding make a visual asset appear inexplicably small.

## Time and recovery

- Run runtime, font, package and finalization preflights before any ImageGen
  call or PPTX build.
- Reuse an asset only when its source hash, prompt/cache key, delivered hash,
  identity/color QA and local-crop QA all match.
- Retry only the failed asset. Placement-only defects consume a layout repair,
  not another ImageGen call; identity/color/alpha defects consume an
  asset-level retry.
- Generate compatible assets with bounded concurrency or a safe intermediate
  batch. Do not serialize unrelated asset calls or regenerate the whole page.
- Build once, render once, inspect full page plus 3–10 risk crops, then repair
  only the owning object. A one-page run should normally stay within one
  candidate plus the profile's bounded repair candidates.
- Propagate `RUNTIME_NODE`, `RUNTIME_NODE_MODULES` and task-local font paths to
  finalizer child processes. A missing child-process runtime variable is an
  environment failure; fix it before interpreting the deck as failed.

## Acceptance

The final release requires: all inventory visuals covered by independent
ImageGen assets or an explicit user-approved fallback; fresh render evidence;
native formal text; no whole-slide raster; asset/object manifests bound to the
same source hash; and a manual visual comparison of the high-risk crops.
