# Strict image-to-editable optimization validation

The editable worker uses the repository-level maintenance contract in
`ai-ppt-plus` `references/optimization-validation.md`. This local copy keeps
the standalone worker self-contained and is normative for new reference
reconstruction runs.

Record the immutable `main` SHA and preserve all baseline inputs, golden
renders and replay evidence. Resolve missing image paths only through the
bounded workspace/upload/name-variant preflight. Build with JavaScript ESM and
`@oai/artifact-tool`; Python is for inspection/QA only and `python-pptx` is not
a creation or repair fallback. Keep formal text, connectors, semantic shapes
and logical tables native. Independent logos/textures are the only permitted
raster exceptions.

Register and render-test the requested font before authoring and before first
render. Record declared, discovered and actual families, missing weights,
fallback and simulated-bold status. Maintain an exact, human-verified text
ledger and compare it to final `a:t` text. Validate table rich-text child order;
use a bound text-box overlay only as an explicit upstream-compatibility
fallback, with the table still native and movement/reimport tests recorded.

Render the exact finalizer output at the same 16:9 dimensions as the reference
and retain page, side-by-side, overlay, absolute-difference and region crops.
Check semantic layout and object anchors separately from pixel similarity.
Finalization is followed by package, OOXML, import, mutation, font, layout and
render checks. Any replay regression blocks promotion and requires candidate
rollback; no threshold or editability rule may be lowered.
