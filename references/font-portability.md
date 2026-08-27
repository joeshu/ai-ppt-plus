# Font portability and no-blank-text contract

## Required behavior

Formal text must remain real PPTX text, but the deck must carry a declared,
legally redistributable CJK fallback for rendering and delivery checks. Copy
`assets/fonts/NotoSansCJKsc-Regular.otf` and its manifest into the task's
`project-fonts/` directory, then pass `--font-dir project-fonts/` to both
`probe_fonts.py` and `render_pptx.py`.

Use this font priority:

1. A user-supplied licensed font explicitly requested for the project.
2. Microsoft YaHei only when it is already licensed and available on the
   authoring/rendering device; never package or redistribute it.
3. The bundled Noto Sans CJK SC fallback.

## Hard gates

- Never generate a Chinese PPTX with an unresolved font family.
- Never accept a preview that has blank, missing, or substituted Chinese text.
- Run `probe_fonts.py` with the actual task font directory before authoring and
  rerun it during final verification.
- The final render must be produced with the same task-local font directory
  used during authoring. Record the family, file, SHA-256 and license source
  in the delivery report.
- If the authoring backend supports OOXML font embedding, embed the declared
  font and verify the embedded font parts in the final PPTX. If it does not,
  report `embedding: unsupported` and stop final delivery until the user
  accepts a non-embedded delivery; do not claim that a sidecar font is an
  embedded font.

## Device compatibility

Desktop WPS and iPhone WPS may substitute fonts differently. Therefore,
validate the final PPTX render in the requested target environment(s), and
keep text as native text so it remains editable. A font report alone is not
evidence that the PPTX is portable.
