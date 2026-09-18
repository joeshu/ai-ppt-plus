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
asset for those classes by default. If generation fails, pause at a user-
decision gate and present exactly two choices: (1) retry/continue native
`imagegen`, or (2) use deterministic original-image crop/cutout
(`source_reuse`). Never choose either route silently. The selected route,
approver, timestamp and reason must be recorded in the run manifest. If the
user has not selected a route, the asset remains blocked; an unlabelled
fallback, flat fill, generic icon, or full-slide screenshot is forbidden.

Each generated final asset is independent and movable, and its manifest record
must include `asset_id`, `asset_class`, `provenance_mode: imagegen` (or
`source_reuse` only after the explicit fallback decision),
`generated_source`, `copied_to`, `prompt_file`, `backend`, and a delivered-file
hash. Generated assets must not contain formal text, numbers, chart data, or
logos that are authoritative for the page. Formal text remains native rich
text; exact data charts remain native/declared chart objects.

## Exact brand-asset preservation exception

Official brand identity is not an ImageGen reconstruction target. When the
user supplies an exact official brand asset, or explicitly identifies a source
region as authoritative brand artwork, preserve that asset exactly instead of
redrawing or approximating it. This follows the same fidelity principle used by
Knight for supplied real logo/brand marks.

The exception covers independently movable brand furniture whose fidelity
depends on exact artwork, including:

- corporate logos and logo lockups;
- official wordmarks and calligraphic service slogans;
- approved brand signatures/seals;
- official footer/header brand bands that combine a logo/wordmark with a
  skyline, ribbon, 5G mark, campaign signature or other locked brand artwork.

These objects use `provenance_mode: exact_brand_asset`, not `imagegen` and not a
generic `source_reuse` fallback. They must remain independent PPT picture
objects, preserve aspect ratio, use the supplied/canonical pixels without
redrawing, and record source hash plus source/target bbox. Do not OCR and
re-typeset text that is an inseparable part of an authoritative brand lockup.
Do not expand this exception to ordinary icons, decorative art, charts, body
text, cards, or arbitrary screenshot fragments.

If only a slide reference exists and the brand region has not been explicitly
approved as authoritative exact artwork, keep the normal ImageGen/source-reuse
decision gate. A whole-slide or large content-region crop can never be relabeled
as a brand asset to bypass editability requirements.

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
hash. For an approved fallback, the record must additionally include
`fallback_decision: user_approved`, `decision_id`, `decision_reason`, and
source bbox/hash evidence. Exact brand assets instead record
`provenance_mode: exact_brand_asset`, their authoritative source hash and their
independent PPT object ID. A passing visual score cannot waive a route or
provenance failure.
