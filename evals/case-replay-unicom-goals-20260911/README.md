# Unicom goals — real replay case

This is the third real fixed-reference replay case for
`unicom-goals-16x9-fixed-reference-01`.

- Baseline: intentionally flattened one-slide PPTX generated from the approved source image.
- Candidate: native editable PPTX with embedded font data removed for Git delivery size.
- Reference: the original 1536×1024 source image.
- Candidate structure: 94 objects, 38 native text objects, 0 native tables, no whole-slide picture.
- Candidate delivery SHA-256: `4813bfa2d0571e1db690ed3545ed24209d1458586385d495361819c0a30635a1`.
- Original font-bearing QA SHA-256 is retained in `case.json` and the evidence reports.
- The replay gate uses a 0.82 blurred-layout floor because the committed delivery variant intentionally omits the embedded CJK font; structural editability and mutation checks remain mandatory.
- Environment probes, runtime metadata, and the pending human-closeout report are intentionally excluded from this minimal tree.

