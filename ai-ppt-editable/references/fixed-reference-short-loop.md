# Fixed-reference short reconstruction loop

This is the normative execution contract for fixed-reference image-to-editable-PPTX reconstruction. Read `visual-repair-patterns.md` for the reusable defect patterns discovered from fresh-render repair. Read `authoring-plan.md` for the pre-build execution-plan contract. Read `text-coverage-auditor.md` for formal-text producer coverage.

## Production chain

Run exactly this visual reconstruction chain for normal fixed-reference work:

`Ordered Reference/Page Map -> Execution Profile -> Prebuild Execution Preflight -> Visual Inventory -> AuthoringPlan -> native_editable/imagegen_asset -> Risk-tier Text Slot Preflight -> Text Coverage Audit -> Planned Asset Batches -> Asset Generation -> Artifact Tool Build -> Fresh Deck Render -> Per-page Full-page Compare -> Per-page Adaptive Local Crops -> Responsible Object Repair -> Re-render -> Hard Correctness Check -> Final PPTX`

The chain is intentionally visual-first. PageGraph, TextGraph, manifests, metrics and reports support reconstruction and repair; they do not become independent visual release gates.

## Phase contract

1. **Ordered Reference/Page Map** — resolve every current-turn image in the
user's attachment order; freeze one row per intended slide with resolved path,
dimensions, aspect ratio and SHA-256. For N images, bind image N to slide N and
make exactly N slides unless explicitly requested otherwise. Do not sort,
silently skip missing pages, deduplicate identical images or insert a cover.
For multi-image execution, follow `multi-image-reference-deck.md`.
1A. **Execution Preflight** — run reference-input resolution once for the
complete ordered roster. Before ImageGen or authoring, validate package
revision parity, resolved source, runtime Node/modules, CJK font evidence and
LibreOffice+Poppler. Before ImageGen or the first candidate build, run
`scripts/validate_finalization_preflight.py` so missing runtime exports,
receipt directories or final-path conflicts fail before visual repair rounds.
2. **Visual Inventory** — inventory visible text, panels/cards, charts, semantic tables, repeated components, arrows/connectors, icons/logos, complex art and composed semantic regions such as header/footer systems. Assign stable object IDs and approximate source bboxes and relationships.
3. **AuthoringPlan** — convert inventory into explicit authoring decisions before build: implementation type, semantic role, bbox, parent, z-role, anchors, protected neighbors and type-specific contract. Validate `authoring-plan.json` before authoring. This is a structural pre-build contract, not a visual score gate.
4. **Classification** — classify every non-text visual as exactly `native_editable` or `imagegen_asset`. Readable formal text stays native. Semantic tables/charts stay native when their meaning/data are known. Reference pictograms/icons are `imagegen_asset` by default unless their visible identity can be faithfully expressed by at most two ordinary native primitives. Complex footer waves, skylines, ribbons/streams and artistic systems may be one or a small number of independent semantic assets.
5. **Text Slot Preflight** — measure every visible native text slot before authoring. Preserve the reference's exact line topology when observable, not merely a maximum line count. Repair bbox, margins, divider/icon reservations and wrapping before shrinking type. Use the same runtime-resolved font face for measurement and authoring.
6. **Text Coverage Audit** — require every formal-text producer to bind to an AuthoringPlan owner, TextFit measurement evidence, concrete authoring path and final output binding. Native-text owners may not bypass this audit. Missing coverage is a formal-text/provenance correctness defect, not a visual score failure.
7. **Planned Asset Batches** — inventory all pages before the first expensive
generation call and plan compatible simple icons across the deck. Respect the
machine limits (`fast`: at most 4 cells per call; `strict`: at most 3); a
manual prompt must never bypass the planner's cap. Brand/wordmark/calligraphy,
wide bands and complex art use dedicated native ImageGen calls. Retain rejected
candidates only in a separate generation log.
8. **Asset Generation** — generate every approved `imagegen_asset` with
genuine RGBA alpha. Slice accepted icon batches into independent pictures and
give each final asset its own stable ID, ImageGen receipt linkage, byte hash,
identity/contour, alpha bbox, safe-padding, clipping and placement QA. The
delivered-asset manifest lists only final bytes actually embedded in the PPTX;
unused attempts belong in the generation log. Source crops are evidence, not
silent final-asset fallback.
9. **Artifact Tool Build** — build a fresh editable PPTX through the strict `@oai/artifact-tool` authoring path. Preserve AuthoringPlan object IDs and independent asset mobility. Never use a whole-page screenshot as the editable reconstruction. Where parent/child relationships matter, author children relative to the semantic-region geometry rather than unrelated page coordinates. Material deviations from AuthoringPlan must be written back to evidence and revalidated.
10. **Fresh Deck Render** — render every page from the exact current PPTX. Historical per-page renders cannot satisfy this phase after a merge or rebuild.
11. **Per-page Full-page Compare** — compare slide N only to the source mapped to N. Scalar metrics are diagnostic only unless a project explicitly supplies a numeric target.
12. **Per-page Adaptive Local Crops** — cut same-coordinate crops from each page render. Select 3-5 high-risk regions per page in `fast` or 5-10 per page in `strict`, prioritizing dense text/cards, icon slots, charts, compact arrow+label components, bottom bars and user-flagged areas. Include composed header/footer semantic-region crops when present.
13. **Responsible Object Repair** — every material mismatch is assigned to the owning object/layer or semantic region. Repair that owner rather than compensating through unrelated neighbors or chasing a scalar score. Protect already-correct regions. Use AuthoringPlan `protected_neighbors` and the pattern-specific repair order in `visual-repair-patterns.md`.
14. **Re-render** — every accepted material repair must be followed by a fresh full-deck render and re-check of affected crops plus every page.
15. **Visual Closeout Consistency** — write structured reference/candidate observations for required material region roles and validate them with `scripts/validate_visual_closeout.py`. An unresolved visual finding is unfinished repair work, not a score threshold. Contradictory closeout evidence blocks PASS and returns to repair.
16. **Hard Correctness Check** — only deterministic correctness defects and unresolved evidence-consistency defects block delivery. Visual metrics remain diagnostic.
17. **Final PPTX** — deliver only the fresh candidate that passed hard correctness and visual-closeout consistency checks and whose final per-page/crop evidence corresponds to the delivered hash.

## The only production hard blockers

Normal fixed-reference reconstruction may be blocked only by these categories:

- `corrupt_or_unrenderable`: output is corrupt, cannot be opened, or cannot be rendered.
- `formal_text_loss`: required readable/formal text is missing or materially altered.
- `whole_slide_raster_fallback`: a whole-slide bitmap is used to impersonate editability.
- `required_editability_loss`: required native/editable objects are flattened or unavailable for editing.
- `asset_missing_or_invalid_alpha`: a required independent asset is missing, has fake/empty alpha, unsafe clipping, or non-transparent edge contamination.
- `severe_overflow_collision_oob`: severe text/object overflow, collision, or out-of-canvas geometry.
- `semantic_table_misclassification`: a repeated information/card component is incorrectly authored as a semantic table, or a true semantic table loses its row/column meaning.
- `chart_blank_serialized_as_zero`: unknown/blank chart values are serialized as zero or otherwise fabricated.
- `source_or_provenance_mismatch`: the candidate/evidence does not derive from the frozen source or required generated-asset provenance is missing.

Do not add SSIM, pixel score, five-dimensional A/B score, PageGraph completeness, report count, Runtime Mirror status, Perfect Sync status, package-validation status, or external-comparator availability to this production hard-blocker list. Those may remain development/CI diagnostics or environment prerequisites, but they must not turn a visually repairable page into a visual release failure.

## Diagnostic evidence, not blockers

Use whole-page SSIM, regional SSIM, pixel diff, bbox IoU, centroid drift, scale drift, text-fit utilization, icon similarity and five-dimensional A/B to rank repairs and detect regressions. A poor diagnostic result must create or reprioritize a repair item. It must not by itself terminate normal production execution.

Do not use a fixed `score < 0.90` rule to decide whether a repair item exists. Rank by relative mismatch, material area, semantic importance and explicit visual findings. Inspect the 3-5 highest-impact regions per iteration even when scalar scores are high enough to hide obvious contour, typography-density or anchor defects.

External comparator A/B belongs exclusively to development regression evaluation. Production execution must not discover, invoke, import, or depend on an external comparator.

## Repair-loop policy

Each repair item records: page, crop/object IDs, mismatch description, responsible layer, proposed delta, before evidence, after evidence, acceptance/rejection and reason. Prefer the 3-5 highest-impact material defects per iteration. Re-render after each coherent repair batch. Reject a repair that fixes one crop by materially regressing the full page or another protected crop.

Repeated components may use component-local geometry. Do not force identical divider positions, icon slots, text widths or font scales when the reference visibly differs. Semantic consistency does not require geometric uniformity.

Complex visual systems may be a single or small number of independent semantic assets when native fragmentation would reduce fidelity. Keep readable text and ordinary semantic geometry native above/beside those assets. Parent geometry must be repaired before child anchors such as `5Gⁿ`, logos or footer slogans.

## Bounded convergence and render authority

For a one-page reconstruction, default to one initial candidate plus at most
two coherent repair batches. A third repair round requires an active hard
correctness defect or an explicit budget-exception reason in the short-loop
report. Batch the 3 highest-impact material regions; do not create a new PPTX
variant for each text box, icon or metric change. Run cheap text-fit, geometry,
asset-path and finalization preflights before each expensive build.

Use Microsoft PowerPoint export as the final visual renderer for reference
comparison and closeout. LibreOffice+Poppler is a provisional iteration render
when PowerPoint is unavailable; Artifact Tool import/preview evidence proves
package structure and compatibility only. Do not repair large title typography
solely around LibreOffice-specific kerning or line wrapping. Whole-page and
regional similarity scores rank repair work; they never force another round by
themselves.

Inspect header/brand, footer/edge system and other composed parent regions
before child anchors. Validate generated asset aspect ratio against its target
slot before authoring; create one documented layout-normalized derivative when
the source aspect ratio cannot satisfy the slot, rather than discovering the
problem after a full build.

## Acceptance

Final acceptance requires: current-source hash match; fresh PPTX/render hash linkage; full-page review; profile-compliant same-coordinate crops cut from that render; structured visual-closeout validation with no unresolved material findings; no unclosed text-render repair records; exact formal-text ledger; editability/object inspection; independent asset alpha/provenance QA; semantic chart/table checks where applicable; zero hard blockers; and a Repair Trace for the last accepted material changes.
