# Font portability and no-blank-text contract

## Required behavior

Formal text must remain real PPTX text, but the deck must carry a declared,
legally redistributable CJK fallback for rendering and delivery checks. For
weight-sensitive decks, carry the complete static face set
(`NotoSansSC-Regular.ttf`, `NotoSansSC-Medium.ttf`, `NotoSansSC-SemiBold.ttf`,
and `NotoSansSC-Bold.ttf`) and its manifest in the task's `project-fonts/`
directory. Register every face under the same renderer alias and pass the
directory to the font probes.

For a Chinese deck, also copy the bundled font into the task font directory
before the first font probe; do not rely on the host's installed-font list.

Use this font priority:

1. A user-supplied licensed font explicitly requested for the project.
2. The bundled Noto Sans CJK SC fallback (the manifest's canonical family name).
3. Microsoft YaHei only when explicitly requested, already licensed and
   available on the authoring/rendering device; never select or package it
   implicitly.

After copying a task-local font set, run
`scripts/validate_font_asset.py --font-dir project-fonts/ --require-cjk
--require-weights --report font-asset-validation.json`. This validates the
manifest hash, the declared family, a representative CJK glyph set, the
license declaration and the raw SFNT family/style/weight metadata. The weight
gate requires real 400/500/600/700 faces; a simulated bold face is not a
replacement for the set.

For a legacy single-face project, omit `--require-weights` and preserve the
missing-weight finding in the report. This validates the manifest hash, the
declared family, a representative CJK glyph set, the license declaration and
the raw SFNT family/style/weight metadata; font discovery alone is not
asset-integrity evidence. A manifest that calls a file Regular while its
default SFNT face is Thin or ExtraLight is invalid, even if fontconfig lists a
regular named instance for the same variable file.

## Hard gates

- Never generate a Chinese PPTX with an unresolved font family.
- Never accept a preview that has blank, missing, or substituted Chinese text.
- Run `probe_fonts.py` with the actual task font directory before authoring and
  rerun it during final verification.
- The final render must be produced with the same task-local font directory
  used during authoring. Record the family, file, SHA-256 and license source
  in the delivery report.
- When a finalizer does not expose native font-render proof, retain its raw
  `native_font_rendering_verified` value and attach independently generated
  artifact-tool registration/render evidence. The compatibility evidence may
  close the actual-render gate, but it must never rewrite the upstream field.
- If the authoring backend supports OOXML font embedding, embed the declared
  font and verify the embedded font parts in the final PPTX. With this
  repository's `python-pptx` composer, use `scripts/embed_fonts.py` as the
  post-processor. If neither the composer nor the adapter can embed, report
  `embedding: unsupported` and stop final delivery until the user accepts a
  non-embedded delivery; do not claim that a sidecar font is an embedded font.

## Portable delivery

The final PPTX must be checked from the exact task-local font directory used
during authoring. Keep formal text as native text so it remains editable. A
font report alone is not evidence that the PPTX is portable: combine
`font-report.json`, `font-asset-validation.json`, the final `inspection.json`,
`render-report.json` and `render-visual-gate.json` with
`scripts/validate_font_delivery.py`. The resulting `declared_font`,
`resolved_font`, `render_visible` and (when required) `embedded_font` fields
are separate gates. Device-specific compatibility claims are outside this
skill's automatic release contract and remain human review items.
