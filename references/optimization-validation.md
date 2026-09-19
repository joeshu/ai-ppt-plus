# Image-to-editable optimization validation

This is the repository maintenance contract for reference-image to editable
PPTX work. Preserve editability and deterministic correctness while making the
fresh rendered page the primary source of visual repair evidence.

## Immutable baseline and isolation

Record remote `main` SHA, input filename, dimensions and SHA-256. Never
overwrite a baseline, source, Golden render or replay. Every candidate is an
isolated fresh authoring/render transaction.

## Authoring correctness

New reference reconstruction uses JavaScript ESM plus `@oai/artifact-tool`.
Python is inspection/comparison/QA only. Formal text, semantic shapes,
connectors, tables and known-data charts remain native. Independent complex
visual assets remain independently replaceable. A whole-slide raster is not an
editable reconstruction.

Maintain an exact formal-text ledger and verify final `a:t` text. Resolve and
render-test the declared fonts; record actual family/fallback. Preserve OOXML,
media and rich-text invariants during compatibility normalization.

## Render-driven reconstruction loop

The first valid PPTX is a draft. Optimize in this order:

`reference -> visual inventory -> native/imagegen classification -> fresh PPTX
-> fresh render -> full-page + same-coordinate local crops -> object-level
Repair Trace -> responsible-layer repair -> re-render`.

PageGraph/TextGraph/ChartGraph and validators provide deterministic evidence
and repair coordinates. Do not turn every diagnostic deviation into another
blocking pre-authoring contract. Use the render to decide which object/layer is
actually wrong.

Retain page PNG, side-by-side, overlay, absolute difference and hard-region
crops. Protect regional wins and reject a challenger that causes a real
whole-page replay regression.

## Hard blockers

Fail closed for source/candidate provenance mismatch, corrupt/unrenderable
PPTX, formal-text loss, whole-slide raster fallback, missing required asset,
invalid clipping/alpha, semantic table/list misclassification, chart
missing-value-to-zero corruption, severe overflow/collision/off-canvas layout,
or required-editability loss. These correctness rules are not negotiable.

## Visual metrics and final promotion

Pixel scores are diagnostic during reconstruction. Whole-page SSIM, balanced
reference-fidelity, regional SSIM and crop metrics rank repair work and expose
regressions; they are not the sole reconstruction objective.

When the user supplies no other target, retain 0.90 as the default
reference-fidelity target for **Golden promotion / release-quality assessment**.
A draft below 0.90 may continue through responsible-layer repair and may be
retained as a Hard Negative. It must not be labeled Golden merely because
technical contracts pass. Human approval may accept a documented special case;
automation must never silently lower the target.

Final acceptance combines fresh full-page/local-crop visual review, exact text,
object/editability QA, asset QA, chart/table semantics, Repair Trace and absence
of hard blockers. For external A/B evaluation, run the corrected final
candidate fresh on pixel/layout, text, object/editability, icon/asset and
local-crop dimensions; historical scores are not substitutes.
