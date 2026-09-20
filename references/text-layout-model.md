# Text layout model

`text-layout-manifest.json` is the canonical text and typography contract for a page. It uses `TextSpec` records for text boxes and `TextRunSpec` records for mixed styling. The formal string is `content`; when `runs[]` exists, concatenating their `text` values must reproduce it exactly, including line breaks and literal redaction tokens. TextFit uses the same precedence rule: a declared rich-run sequence is the measured authority, never a stale parallel `text` field.

Each `TextSpec` records a stable `text_id`, source reference, optional source-coordinate `source_bbox`, final `bbox`, coordinate space, base typography, wrapping behavior and optional `emphasis_expected`. `style` may use `font_family`/`font`, `size_pt`, `size_px`, `size_ratio` or `size_pct`, color, weight, alignment, line spacing and margins. A Run contains only its text and style overrides. Each run has a stable `run_id`; the coverage ledger preserves ordered run text, style and hashes so the authoring path can be audited back to the TextSpec. An explicit `number_unit` group may bind number/unit run IDs, but digit-like strings are never guessed into that producer class. `source_bbox` is required for reference-reconstruction because it replays a source viewport; it is not required for visual-creation, where the generated visual intermediate has no formal text geometry.

Text measurement evidence declares `measurement_scope.kind` as `whole_phrase`
or `sub_box`. Whole-phrase measurement is the default for mixed-size or
mixed-color runs; a sub-box is a separately named text target, not an implicit
manual `add_run` escape hatch. `content_sha256` and `run_style_sha256` make
the measured content/style trace reproducible.

Create and validate it with the standard-library tool:

```bash
python3 scripts/text_model.py build layout.json --output text-layout-manifest.json
python3 scripts/text_model.py validate text-layout-manifest.json \
  --require-source-bbox --report text-layout-validation.json
```

For exploratory layouts, missing boxes or typography are warnings. Strict reference reconstruction promotes warnings to blockers. The model never rewrites formal text, invents missing content or treats a logo wordmark as ordinary text. Existing `layout.json` and `validate_text_style_map.py` remain supported during migration.

## Measured reference line boxes

Reference-reconstruction should carry `reference_line_count` and measured `reference_line_boxes` for authoritative text slots, in the same source-coordinate space as `source_bbox`. When `require_measured_line_boxes: true`, the editable worker fails closed if a declared reference line topology lacks measured line boxes. Visual-creation does not require this source-only evidence.

PageGraph object geometry is validated separately before typography repair, so font shrinking cannot hide upstream x/y/w/h drift. The final fresh rendered-reference gate remains authoritative for release.
