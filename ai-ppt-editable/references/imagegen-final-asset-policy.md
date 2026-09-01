# ImageGen final-asset policy

This is a post-baseline policy for reference reconstruction. It changes the
final-asset route, not the visual authority: the source image remains the
reference and QA baseline, while the delivered icon/visual asset is generated
independently.

## Mandatory route

The following asset classes must use the native `imagegen` capability for the
final PPT object:

- icons and badges;
- gradient visual/image assets, glows, waves, textures and light effects;
- complex illustrations, decorative art and artistic typography.

`source_reuse` crops are allowed only as reference evidence, crop geometry, or
source-vs-render comparison material. They must never be inserted as the final
asset for those classes. A failed generation is a blocker or an explicitly
labelled placeholder; it must not silently fall back to a source crop, flat
fill, generic icon, or a full-slide screenshot.

Each generated final asset is independent and movable, and its manifest record
must include `asset_id`, `asset_class`, `provenance_mode: imagegen`,
`generated_source`, `copied_to`, `prompt_file`, `backend`, and a delivered-file
hash. Generated assets must not contain formal text, numbers, chart data, or
logos that are authoritative for the page. Formal text remains native rich
text; exact data charts remain native/declared chart objects.

Official brand marks and wordmarks are governed by the brand-asset contract:
use an authorized official source asset rather than asking imagegen to redraw a
legally or visually sensitive logo. This is a brand-asset exception, not a
general source-reuse fallback.

## Required evidence

The run must emit `imagegen-assets-manifest.json` with
`provenance_policy: imagegen_final_assets` and one record per independent final
asset. Run:

```bash
python3 scripts/validate_imagegen_final_assets.py \
  imagegen-assets-manifest.json --strict --report qa/imagegen-final-assets.json
```

Run the validator before composition and after rendering. The post-render
record must identify the delivered PPT object and preserve the generated asset
hash. A passing visual score cannot waive a route or provenance failure.
