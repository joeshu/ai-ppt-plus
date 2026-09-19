# Image-to-editable optimization validation

The editable worker uses the repository-level maintenance contract in
`ai-ppt-plus` `references/optimization-validation.md`. This local copy keeps
the standalone worker self-contained and is normative for new reference
reconstruction runs.

Record the immutable `main` SHA and preserve all baseline inputs, golden
renders and replay evidence. Resolve missing image paths only through the
bounded workspace/upload/name-variant preflight. Build with JavaScript ESM and
`@oai/artifact-tool`; Python is for inspection/QA only and `python-pptx` is not
a creation or repair fallback. Keep formal text, connectors, semantic shapes
and logical tables native. Independent visual assets follow the declared
ImageGen/source-reuse policy.

Register and render-test the requested font before authoring and before first
render. Record declared, discovered and actual families, missing weights,
fallback and simulated-bold status. Maintain an exact, human-verified text
ledger and compare it to final `a:t` text. Validate table rich-text child order;
use a bound text-box overlay only as an explicit upstream-compatibility
fallback, with the table still native and movement/reimport tests recorded.

## Knight-style render-driven repair loop

For fixed-reference reconstruction, the first successfully authored PPTX is a
**draft**, not a release candidate. The primary optimization loop is:

`reference -> visual inventory -> native/imagegen classification -> fresh PPTX
-> fresh render -> full-page review + local crops -> object-level repair trace
-> re-render`.

PageGraph, TextGraph, ChartGraph, asset manifests and deterministic validators
remain evidence and repair inputs. They must catch deterministic defects, but
they must not replace render review or turn every diagnostic deviation into a
new pre-authoring blocker. Repair the responsible object/layer shown by the
render and local crop evidence.

Every iteration retains the exact finalizer output at the same 16:9 dimensions
as the reference and retains page, side-by-side, overlay, absolute-difference
and hard-region crops. Check semantic layout and object anchors separately from
pixel similarity. Any replay regression against the selected incumbent is
rejected and rolled back.

## Gate classes

### Hard blockers

Fail closed for deterministic correctness failures: stale/mismatched source or
candidate provenance; corrupt/unrenderable PPTX; missing or altered formal
text; whole-slide raster masquerading as editable reconstruction; missing
required independent asset; invalid alpha/clipping for required assets;
semantic table/list misclassification; chart missing-values serialized as
zero; severe overflow/collision/out-of-canvas geometry; or loss of required
editability.

### Diagnostic visual metrics

Whole-page SSIM, blurred layout/color fidelity, regional SSIM and crop metrics
are **diagnostic during the repair loop**. They rank repair work, protect
regional wins and reject whole-page regression, and are never a universal pass/fail threshold for ordinary execution. Raw pixel
fidelity is always diagnostic because renderer/font antialiasing varies.

### Final acceptance and Golden promotion

Final acceptance requires fresh rendered evidence plus local-crop review,
formal-text equality, object/editability QA, asset QA and absence of hard
blockers. There is no built-in 0.90 or other universal numeric target for normal delivery. Numeric visual thresholds are opt-in project parameters only. Final acceptance is based on fresh render review, same-coordinate local crops, exact formal text, object/editability QA, asset/alpha QA, semantic correctness and absence of hard blockers.

External A/B evaluation is optional and separate from normal execution. Ordinary image-to-editable runs must be self-contained and must not depend on another skill being installed or runnable.
