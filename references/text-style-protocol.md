# Text-style reconstruction protocol

## Purpose

Image-to-editable-PPT work has two separate text contracts:

1. **Content contract**: the reconstructed string is faithful to the approved
   source, including redactions, punctuation and line breaks.
2. **Visual-style contract**: emphasis, color, weight, size, spacing, alignment,
   wrap width and text-box bounds are faithful to the reference.

The first contract can be satisfied while the second is broken. Do not accept
plain black text as a successful reconstruction when the reference uses colored
labels or emphasized numbers.

## Required text map

For every visible text region, record:

- `name` and `source_bbox` in the full-resolution reference coordinate system;
- `x/y/w/h` in the same reference system or normalized fractions;
- base `font`, `size`/`size_px`, `color`, `bold`, `line_spacing`, alignment and margins;
- `runs[]` for any mixed styling. Each run has its own text plus only the style
  overrides it needs. Concatenating all runs must reproduce the source string.

Use runs for section labels, bullets, numbers, prices, percentages, redacted
placeholders, colored title accents and footer segments. Preserve literal
redaction glyphs from the source. If the source visibly uses `**元` or another
masking token, mark the item/run with `literal_redaction:true`; otherwise
Markdown markers must not appear in visible PPT text.

## Two-pass workflow

1. Transcribe the complete source text without rewriting.
2. Mark every style transition and measure each text box from the full-resolution
   source, not a palette thumbnail or contact sheet.
3. Run `validate_text_style_map.py layout.json --require-source-bbox`.
4. Compose native text and render with the same task-local font directory.
5. Compare line breaks, emphasis and the text-to-illustration boundary. If a
   run contains a newline, the preview renderer must measure it line by line.

## Acceptance rules

- `validate_text_style_map.py` errors are blockers.
- Plain text containing likely emphasis tokens is a warning that requires visual
  review; promote it to an error for a reference reconstruction whose source is
  legible.
- A missing `source_bbox` is a QA warning for exploratory work and a blocker for
  strict reference reconstruction.
- “Font rendered locally” and “font embedded in PPTX” are different claims;
  report them separately.
