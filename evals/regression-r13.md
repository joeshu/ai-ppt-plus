# R13 regression baseline

Baseline case: `存量双终端优秀案例`.

R13 freezes the reconstruction behavior before later font experiments. It is the accepted visual baseline for:

- B4/B5 ImageGen icon extraction, chroma keying, splitting and contact-sheet review;
- logos/product images/illustrations treated as explicit assets rather than accidental screenshot fragments;
- scene-aware icon composition instead of a hard-coded colored-disk pattern;
- text run-level emphasis for color and weight;
- desensitized `**元` retained as formal text when the source is masked;
- broad complex gradient atmosphere routed to B2 `background_blend`;
- frame/container gradients routed to B3 and independent product/Wi-Fi/icon elements retained as B4;
- final PPTX render verification with decoded-PNG checking and pdftocairo fallback.

Known open issue intentionally excluded from the R13 baseline: cross-device font parity between desktop WPS and iPhone WPS. R14/R15 font experiments are not part of this baseline.

## Freeze rule

The accepted R13 artifact set is frozen outside the skill source tree with
`scripts/revision_guard.py freeze`. It includes the authoritative PPTX, the
original source/reference image, the preview rendered from that PPTX, the
approved manifests, quality reports, supporting assets and SHA-256 evidence.
Later repairs must use a new revision and must not overwrite the R13 archive.
