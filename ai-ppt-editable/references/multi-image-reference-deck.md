# Multi-image reference deck workflow

Use this workflow when the user supplies two or more slide images and asks for
one editable deck. Each image is a page-level authority; the deck remains
editable content, not a stack of reference screenshots.

## Ordered page map

1. Resolve the complete current-turn image roster using
   `source-intake.md` and `scripts/reference_input_preflight.py`.
2. Freeze one row per source image with its user-supplied order, resolved path,
   dimensions, aspect ratio, SHA-256 and any transcription caveat.
3. Bind source row `N` to PPTX slide `N`. Keep exactly the supplied page count,
   with no automatic cover, deduplication or content merging.
4. Build the whole deck from that map. Keep each page's text, charts, tables,
   icon inventory and provenance attached to its owning source hash.

If a source page is unreadable or cannot be resolved, identify the page and
stop that page before generation. Do not shift later images forward to fill the
gap.

## Efficient generation and safe page reuse

Plan the complete deck's generated visuals before the first ImageGen call.
Group only compatible simple alpha icons within the active profile limit
(`fast`: at most 4; `strict`: at most 3). Never create a larger sprite sheet
and later treat truncation/slicing errors as acceptable. Logos, wordmarks,
calligraphy, wide bands and complex art always get dedicated generation calls.
Every delivered icon cell becomes an independent picture with its own
`asset_id`, alpha/identity QA and final-byte hash.

A previously reconstructed page may be reused only when its source SHA-256 is
identical to the current page, its native-editability inspection passes, and
its asset manifest hashes are still present. Reuse the editable slide object,
not a render or screenshot. Record the reused source SHA and artifact path.
Regenerate only the changed page when the hash differs. The final combined
deck still requires a fresh render, full-deck review and per-page comparison;
historical page renders cannot serve as final-deck evidence.

An identical source hash permits reuse of the editable object, but does not
certify visual quality. In a merged deck, inspect the reused page's title,
subtitle, brand lockup, and footer against the current attachment again.
Correct defects in the reusable slide or in the imported editable objects.

## Deck-wide verification

Use a stable reference roster (`slide-1.png`, `slide-2.png`, …) and validate
the complete exported deck against it. The finalizer must confirm the expected
page count and shared slide geometry. Render every page from the exact final
PPTX, then compare page `N` only with reference `N` and cut the profile's
required same-coordinate high-risk crops from that same render. Include at
least one text-dense region and one visual/asset region per page, plus composed
header/footer bands where present.

Before marking any crop as reviewed, record the source's **information
topology**: table row labels and value columns, plus signs or arrows between
offer components, label rails, nested panels and emphasis colors. Compare the
rendered crop with this inventory. Reject a merged table row, a missing
relationship mark, a displaced brand lockup, or title/subtitle collision even
when all OCR words and object counts are present. A numeric image score alone
cannot certify these structures. Review full-slide pairs after crop fixes so
one region's repair does not move another.

For small or blurred source text, transcribe only legible wording. Preserve
the source's layout with editable text fields, and mark unreadable spans in
speaker notes or a transcription manifest. Never silently replace the source
with plausible new sales copy or an expanded summary. Check every claim in
new text against the visible source before final delivery.

For source text with mixed emphasis, inventory each colored/bold span within
its original line before writing text. Use native character runs (or adjacent
native text fields when line geometry demands them) to preserve the exact
highlight boundaries. A visually similar all-black paragraph fails the text
fidelity review even if its words survive. Inspect the rendered tight crop at
slide size and ensure colored spans do not shift to a neighboring line.

For an existing multi-page deck, use the deck-level pipeline route with
`--reference-dir` and `--require-multipage-layout`; a single-reference
first-page comparison is never evidence for the whole deck. If the authoring
workflow uses per-page strict releases, merge only the native editable pages,
then still run the deck-level checks on the merged final PPTX.

Inspect the final deck's per-page counts and ensure no page became a full-slide
picture during merge. Bind final render reports, image provenance and crop
evidence to the final PPTX SHA-256. Report only render authority actually
available (PowerPoint versus provisional LibreOffice+Poppler).

## Closeout manifest

Keep the page/source crosswalk in the project and final handoff:

| Slide | Current source SHA-256 | Final page render | Key regions checked | Editability evidence |
|---:|---|---|---|---|
| 1…N | one exact hash per source | one fresh render per page | per-page crop IDs | native text/shape/picture counts |

Keep unused/rejected generated candidates in a separate generation log. The
final embedded-asset manifest contains only assets that are actually present
in the delivered PPTX; validate each listed byte hash against `ppt/media/`.
This prevents unused first-pass images from creating false missing-asset
failures or obscuring which generated objects ship.
