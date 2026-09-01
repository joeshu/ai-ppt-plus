# Source-crop integrity adapter

This post-baseline adapter closes a gap in the frozen asset provenance gate.
`source_sha256` and the delivered asset hash prove that two files are current;
they do not prove that the delivered asset was cut from the declared source
coordinates.

For an exact source reuse, the asset record must include:

- `source_crop_policy: exact`;
- `source_crop_sha256`, the canonical RGBA pixel hash of the declared
  `source_bbox`; and
- a delivered `copied_to` image whose pixel dimensions and canonical RGBA
  pixels match that crop.

If alpha trimming or another deliberate processing step changes the pixels,
use `source_crop_policy: derived`. The validator still verifies the declared
source crop hash, while the processing step and its resulting asset hash stay
in the ordinary asset manifest for visual review.

Run it for every strict reference-reconstruction job:

```bash
python3 scripts/validate_source_crop_integrity.py \
  imagegen-assets-manifest.json \
  --report qa/source-crop-integrity.json
```

The adapter is intentionally separate from the synchronized perfect-first
validator. It can therefore strengthen source reuse without changing the
frozen baseline algorithm or silently changing the image-generation route.
