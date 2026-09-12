# Strict image-to-editable optimization validation

This is the current post-baseline maintenance contract for image/reference to
editable PPTX work. It supplements the repository's existing reconstruction,
native-object, font, OOXML and finalization references. It does not lower any
editability, visual-fidelity or release gate.

## Immutable baseline and isolation

Record the remote `main` SHA, worktree state, input file name, dimensions and
SHA-256 before changing code. Copy references only into a derived run
directory. Never overwrite a checked-in replay, input, baseline deck or golden
render. A candidate that introduces a new finding, warning, rasterized
semantic object, missing character, silent font substitution or visual
regression is rejected and its evidence is retained.

## Input and font evidence

Run `scripts/reference_input_preflight.py` before formal authoring. It may
resolve a missing old path from the current attachment/workspace `upload/`
directory and deterministic upload-name variants, but it must block when
different candidate hashes remain. The report is the page-order manifest.

Run `scripts/probe_fonts.py` before creation and before first render. Register
the selected font through the shared runtime adapter in the builder,
artifact-tool renderer and final QA renderer. A package declaration is not
render evidence. `font_render_smoke.mjs` must prove Chinese title/body,
mixed CJK/digits, bold or simulated bold, red/blue emphasis and modified text
re-export. Record declared, discovered and actual render families, missing
weights, fallback and simulated-bold status. Never silently replace a font.

## Native authoring and OOXML

New reference reconstructions use the `strict_authoring` route: JavaScript ESM
and `@oai/artifact-tool`. Python is limited to inspection, comparison and QA;
`python-pptx` must not create, repair, reopen or resave the final deck.

Formal text, numbers, punctuation, formulas, arrows, connectors, semantic
panels and logical tables remain native. Independent logo or texture images
must be separately replaceable and must not contain baked formal content.

If artifact-tool emits rich-text runs, validate the schema order of
`a:rPr`, `a:defRPr` and `a:endParaRPr` before delivery. ZIP-level normalization
may repair only that known order and must preserve slide parts, media bytes,
text/style digests, relationships and gradients. A controlled text-box overlay
is allowed only when the upstream exporter cannot represent the cell run: the
table remains native, the binding to the target cell is recorded, movement and
reimport are tested, and the exception is called out in QA. Prefer direct
native cell text and reject unnecessary overlays.

## Text, layout and visual closure

Maintain a reference text ledger with page, region, exact text, punctuation,
digits, colors, weight, OCR confidence and human verification. OCR is
auxiliary. Low-confidence characters require enlarged crops and manual
confirmation. Compare the ledger to final `a:t` text at character level,
including title, formula, date, unit, amount, percentage and red-emphasis
checks.

Normalize the reference to the final renderer's exact 16:9 dimensions and
render the exact finalizer output. Produce final page PNGs, side-by-side,
semi-transparent overlay, absolute-difference and required-region crops. Run
semantic layout checks for overflow, unexpected line breaks, obscuration,
arrow crossings/endpoints, table borders, z-order and off-canvas objects.
Record object anchors, baselines, row heights and column widths. Pixel scores
are diagnostic only; visible differences require rework.

## Reproducibility and release

Builders take input, output, font, repository SHA and QA directory as explicit
arguments; runtime Node/modules are discovered from the configured environment
or an explicit override. Temporary staging and final delivery directories are
separate. Finalizers never silently rename an existing target: use an explicit
versioned output or an explicit controlled replacement. Write a source
manifest containing input/font/build/final/renderer/finalizer hashes and
independent image asset records.

After finalization rerun package integrity, page size/count, OOXML order,
layout, font delivery, artifact-tool import, text/table mutation and exact
final render checks. Re-run every real replay case. All original passes must
remain passes, and no gate may be weakened to make a candidate pass.
