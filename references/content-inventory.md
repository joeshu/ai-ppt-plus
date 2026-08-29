# Visible-content inventory

`content-inventory.json` is the independent source-review record for a
reference-led page. It is not generated from the final PPTX or copied from the
layout file. It records every visible formal text item and every visible chart
annotation that must survive reconstruction.

Set the top-level `authority` to `approved_outline`, `user_transcription`, or
`approved_outline_or_user_transcription`. When `source_reference` points to a
local file, also record its lowercase `source_sha256`; the validator checks it
against the current bytes. A pending or invented authority is invalid for a
strict release.

Each page lists `visible_text[]` and, when applicable, `charts[]`. Every text
entry has a stable `object_id`/`text_id`, exact `content`, semantic `role`,
`source_bbox`, and `required: true`. Chart entries must declare an explicit
`representation`, `source_data_status`, `required_elements`, and a non-empty
`visible_elements` list for each required element. Typical elements are
`category_labels`, `series_labels`, `data_labels`, `legend`, `units`, and
`axis_titles`; if an element is absent in the source, omit it from
`required_elements` and record that decision in the issue log.

The inventory must be reviewed before composition and validated with:

```bash
python scripts/validate_content_inventory.py content-inventory.json \
  --object-manifest slide-object-manifest.json \
  --text-manifest text-layout-manifest.json \
  --deck editable.pptx --expected-pages N \
  --report content-inventory-validation.json
```

The gate checks page coverage, duplicate IDs, complete editable-text coverage,
object/text-manifest agreement,
native text-box identity, exact PPTX text, and chart annotation completeness.
For a native chart, `source_data_status` must be `verified` and the source
data/hash evidence must be carried by the object manifest. For a static chart
or SVG fallback, the visible labels still remain native text objects; the
fallback does not excuse missing months, legends, units, or data labels.

Do not use a screenshot crop as the only evidence for formal text. If OCR is
unavailable, keep the transcription authority explicit (`approved_outline` or
`user_transcription`), mark uncertain text `待验证`, and require human
confirmation before release.
