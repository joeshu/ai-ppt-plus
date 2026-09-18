# ImageGen final-asset policy

This is a post-baseline policy for reference reconstruction. It changes the
final-asset route, not the visual authority: the source image remains the
reference and QA baseline, while the delivered icon/visual asset is generated
independently.

## Mandatory route

For image-to-editable reconstruction, use one deterministic classification:
formal text/data and simple native PowerPoint primitives stay native; every
other non-native visual asset must use native `imagegen` for the final PPT
object. Do not add a brand-exception classification step.

The mandatory ImageGen classes include:

- icons and badges;
- corporate logos, logo lockups and brand marks reconstructed from the reference;
- wordmarks, calligraphic service slogans, signatures and seals;
- footer/header brand bands, skylines, ribbons, 5G marks and other locked brand artwork;
- gradient visual/image assets, glows, waves, textures and light effects;
- complex illustrations, decorative art and artistic typography.

The source crop is reference evidence, prompt guidance, bbox/geometry evidence
and the crop-QA baseline. It is not the final PPT asset.

`source_reuse` crops are allowed only as reference evidence, crop geometry, or
source-vs-render comparison material. They must never be inserted as the final
asset for these classes by default. If generation fails, pause at a user-
decision gate and present exactly two choices: (1) retry/continue native
`imagegen`, or (2) use deterministic original-image crop/cutout
(`source_reuse`). Never choose either route silently. The selected route,
approver, timestamp and reason must be recorded in the run manifest. If the
user has not selected a route, the asset remains blocked; an unlabelled
fallback, flat fill, generic icon, or full-slide screenshot is forbidden.

Each generated final asset is independent and movable, and its manifest record
must include `asset_id`, `asset_class`, `provenance_mode: imagegen`,
`generated_source`, `copied_to`, `prompt_file`, `backend`, and a delivered-file
hash. Formal body text, ordinary labels, numeric data and verified chart data
remain native/declared semantic objects and may not be rasterized into these
assets.

## Brand visual reconstruction

Brand visuals use the same ImageGen route as other complex visual assets. There
is no automatic `exact_brand_asset` fast path for screenshot/reference
reconstruction.

For each brand visual:

1. measure/crop the source region only as reference evidence;
2. record bbox, aspect ratio, dominant colors, alpha requirement and semantic role;
3. invoke native ImageGen to reconstruct the visual at high resolution;
4. require transparent RGBA when the visual overlays slide content; if direct
   alpha fails, follow the normal transparent-edit/chroma-key fallback policy;
5. keep the generated source and final transparent asset separately;
6. place it as an independent movable PPT picture using visible-alpha bbox and
   alpha-centroid alignment rather than opaque canvas bounds;
7. compare the rendered same-coordinate local crop against the reference and
   regenerate/repair when fidelity is inadequate.

A brand lockup whose lettering is inseparable from its artwork is generated as
one visual asset; do not OCR/re-typeset its internal artwork. This does not
permit normal presentation copy to become raster text.

Only when the user explicitly supplies an authoritative standalone brand file
and explicitly asks to insert that exact file may the run use it directly.
That is a user-directed source operation, not an automatic skill exception.
Without that explicit instruction, ImageGen remains mandatory.

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
hash. For a user-approved source-reuse fallback, the record must additionally
include `fallback_decision: user_approved`, `decision_id`, `decision_reason`,
and source bbox/hash evidence. A passing visual score cannot waive a route or
provenance failure.
