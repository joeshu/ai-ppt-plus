# Text layout model

`text-layout-manifest.json` is the canonical text and typography contract for a page. It uses `TextSpec` records for text boxes and `TextRunSpec` records for mixed styling. The formal string is `content`; when `runs[]` exists, concatenating their `text` values must reproduce it exactly, including line breaks and literal redaction tokens.

Each `TextSpec` records a stable `text_id`, source reference, source-coordinate `source_bbox`, final `bbox`, coordinate space, base typography, wrapping behavior and optional `emphasis_expected`. `style` may use `font_family`/`font`, `size_pt`, `size_px`, `size_ratio` or `size_pct`, color, weight, alignment, line spacing and margins. A Run contains only its text and style overrides.

Create and validate it with the standard-library tool:

```bash
python3 scripts/text_model.py build layout.json --output text-layout-manifest.json
python3 scripts/text_model.py validate text-layout-manifest.json \
  --require-source-bbox --report text-layout-validation.json
```

For exploratory layouts, missing boxes or typography are warnings. Strict reference reconstruction promotes warnings to blockers. The model never rewrites formal text, invents missing content or treats a logo wordmark as ordinary text. Existing `layout.json` and `validate_text_style_map.py` remain supported during migration.
