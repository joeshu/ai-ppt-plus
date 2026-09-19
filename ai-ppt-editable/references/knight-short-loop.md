# Knight-style short reconstruction loop

This is the normative execution contract for fixed-reference image-to-editable-PPTX reconstruction.

## Production chain

Run exactly this visual reconstruction chain for normal fixed-reference work:

`Reference -> Visual Inventory -> native_editable/imagegen_asset -> Text Slot Preflight -> Asset Generation -> Artifact Tool Build -> Fresh PowerPoint Render -> Full-page Compare -> 5-10 key Local Crops -> Responsible Object Repair -> Re-render -> Hard Correctness Check -> Final PPTX`

The chain is intentionally visual-first. PageGraph, TextGraph, manifests, metrics and reports support reconstruction and repair; they do not become independent visual release gates.

## Phase contract

1. **Reference** — freeze source page, dimensions, aspect ratio and SHA-256. The current source image is the immutable visual authority.
2. **Visual Inventory** — inventory visible text, panels/cards, charts, semantic tables, repeated components, arrows/connectors, icons/logos and complex art with stable object IDs and approximate source bboxes.
3. **Classification** — classify every non-text visual as exactly `native_editable` or `imagegen_asset`. Readable formal text stays native. Semantic tables/charts stay native when their meaning/data are known. Icons, pictograms, complex badges, illustration fragments, ribbons/streams and artistic marks use independent assets.
4. **Text Slot Preflight** — measure every visible native text slot before authoring. Preserve reference line count. Repair bbox, margins, divider/icon reservations and wrapping before shrinking type.
5. **Asset Generation** — generate every `imagegen_asset` independently with genuine RGBA alpha. Validate alpha bbox, safe padding, clipping and visual centroid. Source crops are evidence, not silent final-asset fallback.
6. **Artifact Tool Build** — build a fresh editable PPTX through the strict `@oai/artifact-tool` authoring path. Preserve stable object IDs and independent asset mobility. Never use a whole-page screenshot as the editable reconstruction.
7. **Fresh PowerPoint Render** — render the exact current PPTX. Historical renders cannot satisfy this phase.
8. **Full-page Compare** — compare the fresh render to the immutable reference. Scalar metrics are diagnostic only unless a project explicitly supplies a numeric threshold.
9. **5-10 key Local Crops** — select 5-10 material regions per page, prioritizing dense text/cards, icon slots, charts, compact arrow+label components, bottom bars and user-flagged areas. Use same-coordinate reference/candidate crops.
10. **Responsible Object Repair** — every material mismatch is assigned to the owning object/layer. Repair that object rather than compensating through unrelated neighbors or chasing a scalar score. Protect already-correct regions.
11. **Re-render** — every accepted material repair must be followed by a fresh render and re-check of the affected crop plus the full page.
12. **Hard Correctness Check** — only deterministic correctness defects block delivery. Visual mismatch without a hard correctness defect returns to the repair loop; it does not create a new gate.
13. **Final PPTX** — deliver only the fresh candidate that passed the hard correctness check and whose final full-page/local-crop evidence corresponds to the delivered hash.

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

External Knight A/B belongs to skill-development regression evaluation, not normal user conversion.

## Repair-loop policy

Each repair item records: page, crop/object IDs, mismatch description, responsible layer, proposed delta, before evidence, after evidence, acceptance/rejection and reason. Prefer the 3-5 highest-impact material defects per iteration. Re-render after each coherent repair batch. Reject a repair that fixes one crop by materially regressing the full page or another protected crop.

Repeated components may use component-local geometry. Do not force identical divider positions, icon slots, text widths or font scales when the reference visibly differs. Semantic consistency does not require geometric uniformity.

Complex visual systems may be a single or small number of independent semantic assets when native fragmentation would reduce fidelity. Keep readable text and ordinary semantic geometry native above/beside those assets.

## Acceptance

Final acceptance requires: current-source hash match; fresh PPTX/render hash linkage; full-page review; 5-10 final same-coordinate crops per page unless fewer than five material regions exist; exact formal-text ledger; editability/object inspection; independent asset alpha/provenance QA; semantic chart/table checks where applicable; zero hard blockers; and a Repair Trace for the last accepted material changes.
