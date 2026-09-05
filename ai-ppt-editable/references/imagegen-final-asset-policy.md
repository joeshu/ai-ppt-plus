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
asset for those classes by default.

The bounded retry policy is authoritative. Native image generation is retried
up to three attempts by default. After the third failed attempt the state must
be `user-choice-required`, with exactly the two existing choices:
`continue-native-generation` and `crop-matting-fallback`. The system must not
automatically select either choice.

A crop/matting fallback is valid only when all of the following are recorded:

- `fallback_decision: user_approved`;
- `selected_choice: crop-matting-fallback`;
- non-empty `decision_id`, `decision_reason`, and `decision_timestamp`;
- `native_retry_evidence.status: user-choice-required`;
- `attempts_exhausted >= max_native_attempts >= 3`;
- both legal choices in `native_retry_evidence.choices`;
- one failure record for every exhausted native attempt. Each record must carry
  its attempt number, native-imagegen backend, prompt reference, failed status,
  and structured failure evidence (`issue_codes` or `error_code`).

A user approval without exhausted native retry evidence is not sufficient and
must fail closed. Likewise, retry evidence without the user's explicit
`crop-matting-fallback` selection is insufficient. This prevents a direct
`chroma-cutout`, contact-sheet split, source crop, generic icon, flat fill, or
full-slide screenshot from silently becoming the final asset.

Each generated final asset is independent and movable, and its manifest record
must include `asset_id`, `asset_class`, `provenance_mode: imagegen` (or
`source_reuse` only after the complete explicit fallback contract),
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
hash. For an approved fallback, the record must additionally include the full
retry-boundary evidence above plus source bbox/hash evidence. A passing visual
score cannot waive a route or provenance failure.
