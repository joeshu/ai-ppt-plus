---
name: ai-ppt-editable
description: Turn approved slide images, screenshots, rasterized PDF pages, image-slide intermediates, existing PPT/PPTX, or structured content into editable, rendered PowerPoint. Trigger for 图片转可编辑PPTX、截图还原PPT、复刻版式、图标分层、文字提取、现有PPT修复. It can run standalone or as the editable worker for $ai-ppt-plus.
metadata:
  package_revision: 2026.09.25.10
---

# AI PPT Editable

## Mission

Reconstruct or repair editable PPTX with the supplied reference as visual authority and user-provided copy as formal-text authority. For fixed-reference work, visual fidelity is determined from the fresh final render, not from process paperwork or a scalar score.

New strict reconstruction uses JavaScript ESM with `@oai/artifact-tool`. Python is inspection/QA only and is not an authoring fallback. Whole-page raster fallback is forbidden.

Never deliver a fixed-reference deck from a direct composer invocation. Bind the
layout with `route-decision.json` and use the strict reference release path so
font coverage, generated assets, full-page render and local-crop closeout cannot
be bypassed. Strict layout preflight reads real font cmap coverage; a
fontconfig substitute or readable manifest without usable Chinese glyphs is a
blocker. Symbol/emoji text boxes are not production icons.

Read `references/fixed-reference-short-loop.md` for the normative production contract. For two or more source images, also read and follow `references/multi-image-reference-deck.md`; it freezes attachment order, page count, reuse rules, and deck-level validation. Read `references/native-imagegen-runbook.md` for the mandatory native ImageGen call/receipt route, asset provenance and time-bounded recovery rules. Read `references/authoring-plan.md` for the pre-build execution contract. Read `references/text-coverage-auditor.md` for formal-text producer coverage. Read `references/text-slot-repair-planner.md` for TextFit deficit-to-layout repair and `references/text-render-feedback.md` for fresh-render text-region feedback. Read `references/visual-closeout-gate.md` before declaring visual PASS. Read `references/geometry-primitive-resolver.md` for pre-build geometry selection and parameter binding. Read `references/asset-render-coordinate-loop.md` for B5 alpha-space/slot/render-space evidence and continuous-band contour evidence, and `references/protected-repair-planner.md` for B6 constrained repair batches. `references/fixed-reference-fidelity.md` remains implementation guidance. Production execution must not discover, invoke, import, route to, or depend on any external comparison skill. Competitive comparators are development-only artifacts under `evals/`.
Read `references/image-to-editable-regressions.md` when a fresh image-to-editable replay exposes an inventory, alpha-geometry, physical-aspect, text-to-container or composite-anchor defect; apply its stable repair codes and re-render the owning region.
Read `references/top-brand-title-fidelity.md` when the weakest region is a header, brand lockup or large display title; its object-specific crop and PowerPoint-render rules take precedence over whole-slide metric tuning.
Read `references/dense-single-slide-reconstruction.md` for dense 16:9 dashboard/strategy pages with charts, repeated cards and footer bands. It defines the one-pass region inventory, pixel-coordinate normalization, chart uncertainty rule, symbol-font prohibition and CJK render stop condition added after the China Unicom lifecycle-page replay.
For dense red-band layouts, also apply the contrast-aware icon, native bullet geometry and decorative-image underlay rules in `references/image-to-editable-regressions.md`; these prevent invisible icons, renderer-dependent bullets and white-on-white titles when optional artwork fails to decode.
For multi-series fixed-reference charts, keep a point ledger with exact displayed labels and partial-year endpoints; name editable segments, markers and labels, then run `scripts/validate_reference_chart_series.py` before visual acceptance. Check broad rounded-card silhouettes after rendering: uncalibrated corner-radius inputs can turn rectangles into ellipses. Preserve numbered clauses when fitting dense measure rows.
For dense mixed-style bullets, model the colored/bold lead phrase and the body as a shared-baseline line contract. Never force the body into a narrow leftover box that silently shrinks it; measure the combined line and move only the continuation to a full-width next line when necessary. When a source hero contains distinct product families, deliver each family as its own native-ImageGen picture object. Standard widescreen fixed-reference output is exactly 13.333333 × 7.5 inches unless the confirmed source design specifies another page size.

## Formal production chain

For normal fixed-reference reconstruction run this chain and no additional visual release-gate chain:

`Reference -> Execution Profile -> Prebuild Execution Preflight -> Visual Inventory -> AuthoringPlan -> Geometry Primitive Resolution -> native_editable/imagegen_asset -> Risk-tier Text Slot Preflight -> Text Coverage Audit -> Asset Generation -> Artifact Tool Build -> Fresh PowerPoint Render -> Full-page Compare -> Adaptive Local Crops -> Responsible Object Repair -> Re-render -> Hard Correctness Check -> Final PPTX`

Default to the machine-validated `fast` profile in [references/execution-profiles.md](references/execution-profiles.md). Use `strict` only when requested or justified by page risk; use `ci` only for package regression. Profile candidate, render, crop and per-asset retry budgets are hard runtime limits. For a repeatable reference-case replay, write `reference-performance-ledger.json` with `scripts/build_reference_performance_ledger.py`; record total and first-visual time, TextFit time, ImageGen calls, candidate builds, full renders, editable-object counts and visual metrics. Baseline deltas are diagnostic and require rendered-page review, not automatic production rejection.

When invoked by the orchestrator, require `--execution-profile` propagation into editable QA. The execution-budget preflight must pass before composition; performance evidence must report the profile, TTFVR, candidate builds, full renders and uncached ImageGen calls.

Use `scripts/build_imagegen_asset_jobs.py` to batch only compatible simple alpha icons. A batch sheet is a non-deliverable intermediate: slice it into independent transparent assets and run identity, contour, color, alpha and local-crop QA per asset. Never batch logos, brand lockups, calligraphy, wide brand bands or complex illustration. Honor `independent_generation_per_asset: true`. Count one shared generation request once in execution budgets even though every delivered slice retains its own retry and QA record. For every new fixed-reference run, require the native ImageGen tool receipt (`image_gen.imagegen`) in the asset manifest before Artifact Tool composition; a manifest that merely says `native-imagegen` is not sufficient evidence.

Before ImageGen or authoring, pass package/source/runtime/font preflights. After
the first candidate is built—and before any visual repair variant—run
`scripts/validate_finalization_preflight.py`. Bind its reported
`RUNTIME_NODE`/`RUNTIME_NODE_MODULES`, create the private receipt directory,
and resolve output conflicts immediately. For one page, budget one initial
candidate plus at most two coherent repair candidates; require an explicit
hard-defect/budget exception for another round.

PageGraph, TextGraph, ChartGraph, manifests, SSIM, pixel diff, five-dimensional A/B and other metrics may support diagnosis, traceability and regression analysis. They do not replace looking at the fresh render and do not independently block a visually repairable page.

## 1. Reference

Freeze source path/page, dimensions, aspect ratio and SHA-256. Historical PPTX, renders, PageGraphs or crops cannot satisfy a new run. The current source is immutable visual authority unless the user explicitly requests redesign.

## 2. Visual Inventory

Inventory visible text, cards/panels, repeated components, semantic tables, charts, arrows/connectors, icons/logos, decorations and complex art. Assign stable object IDs and approximate source bboxes. The inventory is not a similarity score; its upstream-to-final coverage validation is a correctness gate for fixed-reference source-image work.

For fixed-reference reconstruction, complex visual inventory is also a
coverage contract. Include embedded footer/header calligraphy and decorative
marks, not only standalone icons and logos. Materialize `source-visual-inventory.json` with the locked
source hash, one `visual_id`/`asset_id` per source icon, brand mark,
illustration, decorative art or other complex visual, normalized bbox and
`required_route: imagegen`. An ImageGen manifest that merely lists the assets
it happened to produce is insufficient: run the upstream-to-final coverage
gate and, when a PageGraph exists, cross-check every visual PageGraph node:

```bash
python3 scripts/validate_source_visual_assets.py \
  --inventory PROJECT/source-visual-inventory.json \
  --imagegen-manifest PROJECT/imagegen-assets-manifest.json \
  --page-graph PROJECT/page-graph.json \
  --layout PROJECT/layout.json \
  --report PROJECT/source-visual-assets-validation.json
```

An omitted source visual, missing independent final asset, source-crop
fallback, provenance mismatch or missing final bytes is a blocker. An empty
inventory is valid only when it is explicit and the PageGraph confirms that
the source has no complex visual assets.

When a replay manifest declares a `source_image` baseline, require the
`source_visual_assets_validation.json` result before reporting technical
completion. A missing validation artifact is `NOT_RUN`; a present but blocked
validation is `FAIL`. This keeps a text-fit-complete, card-only approximation
from being mistaken for a faithful image-to-editable-PPTX reconstruction.
Rows explicitly marked `active: false`/`lifecycle: retired` remain available as
diagnostic history and are excluded from the active release denominator.

## 3. AuthoringPlan

Before any authoring, materialize the inventory into `authoring-plan.json`. Every material object must have a stable `object_id`, semantic role, normalized source bbox, implementation type, z-role, parent/child relation when applicable, anchors and protected neighbors. Type-specific authoring intent must be explicit: typography contract for native text, asset contract for ImageGen assets, geometry contract for native geometry, table contract for semantic tables and chart contract for native charts.

Visual Inventory answers what exists. AuthoringPlan answers how it will be authored, where it belongs and what must remain protected. Do not let authoring helpers silently invent or reclassify material objects without writing the decision back to plan/evidence. Validate before Artifact Tool Build:

```bash
python3 scripts/validate_authoring_plan.py PROJECT/authoring-plan.json --json
```

AuthoringPlan structural failures are pre-build correctness failures, not visual-fidelity score gates. See `references/authoring-plan.md` and `assets/authoring-plan.template.json`.

## 4. Geometry Primitive Resolution

Before authoring geometry, resolve each geometry-bearing AuthoringPlan object to the smallest faithful primitive and parameter set:

```bash
python3 scripts/resolve_geometry_primitives.py PROJECT/authoring-plan.json \
  --report PROJECT/geometry-resolution.json --json
```

Use native `FILLED_ARROW` only for a filled body with shaft/head semantics; use `CONNECTOR` for stroke-only two-endpoint paths; use `FREEFORM_BEZIER` for continuous curves; preserve direction/taper for funnels and trapezoids; preserve round-rect adjustment for rounded cards. Complex gradient/3D/glow storytelling geometry routes to `IMAGEGEN_COMPLEX`.

A deterministic AuthoringPlan implementation mismatch is repair-required before build. An unresolved primitive is a blocker because the backend would otherwise guess.

After Artifact Tool authoring, validate cubic/freeform semantics where required:

```bash
python3 scripts/validate_geometry_authoring.py \
  PROJECT/geometry-resolution.json PROJECT/candidate.pptx --json
```

When `FREEFORM_BEZIER` is required, the final OOXML must contain true `a:cubicBezTo` geometry rather than segmented straight-line approximations.
The build must also produce `*.geometry-binding.json`; it is invalid if a resolved page/object target was not present in the Artifact Tool layout.

## 5. native_editable / imagegen_asset

Classify every non-text visual into exactly one practical class before authoring:

- `native_editable`: readable text, cards/panels, dividers, ordinary arrows/connectors, simple badges, semantic tables and native charts whose data/meaning are known.
- `imagegen_asset`: icons, pictograms, complex badges, logos, wordmarks, calligraphic brand marks, decorative art, illustration fragments, artistic marks, complex ribbons/streams, multi-lane gradient arrow systems and visuals whose faithful native reconstruction would require brittle custom drawing.

Brand-class visuals always use native ImageGen for the final asset, including when an exact official/standalone file is supplied. The supplied file or source crop may guide the prompt and provide geometry/color evidence, but cannot bypass generation or become the final asset. Brand classes include `logo`,
`brand`, `brand_lockup`, `wordmark`, `calligraphic_slogan`, `signature`,
`seal`, `brand_band`, `5g_mark` and `locked_brand_art`. A source crop may guide
the prompt and provide geometry/color evidence, but it is never silently cut
out or reused as a final asset. Generate each brand visual as
one independent transparent asset when it overlays the slide; preserve a
complete lockup as one generated asset rather than OCR/retypesetting its
internal lettering. The resulting PPT picture remains movable and replaceable.

Keep readable formal text native. Keep independent visual assets independently movable. Editability is semantic editability, not maximum object fragmentation.

Do not infer a table from borders, repeated rows or two-column alignment. A table requires real field/record/cell semantics. Icon+title+description repetitions remain repeated editable components.

## 6. Text Slot Preflight

For Chinese or mixed Chinese/Latin text, run the fitter with the slot's
semantic role. Treat legal Chinese punctuation wrapping, preserved
Latin/number/unit runs, explicit/reference line topology, target-size box
deficits and hierarchy thresholds as fit evidence. When
`hierarchy_preserved=false`, repair geometry; do not accept the smaller
recommended size as an automatic fix. See `references/text-layout-model.md`.

Measure every visible native text path before authoring. Determine the true editable slot, preserve reference line count and role hierarchy, and use the same runtime-resolved font for fit and authoring. Chinese runs must set Latin/East-Asian/complex-script OOXML typeface metadata as required by the runtime contract.

When text does not fit, repair in this order: text-slot bbox -> margins -> divider/icon reservation -> intended wrapping/line spacing -> role-consistent font adjustment. Do not shrink first. Repeated cards may use component-local divider positions, body widths, icon slots and font scales when the reference differs.

The TextFit Core contract in `references/fixed-reference-fidelity.md` defines the
measurement/report details: CJK character wrapping, intact Latin/number/unit
runs (including symbol-leading values such as `-12.5%`), explicit reference
line-count locking, target-size box deficit evidence and the
`text_slot_first_font_shrink_last` repair policy. `reference_scale` is review
evidence only; it is not a universal numeric release gate.

After `text_fit_deck.py`, do not accept a font reduction merely because it fits. Run `scripts/text_slot_repair_planner.py` so measured box deficits are converted into target-only geometry/margin/dependency/topology repairs first. Font size is the last candidate.\n\n## 7. Text Coverage Audit

After Text Slot Preflight and before build/release acceptance, materialize `text-coverage.json` and audit every formal-text producer path. Every AuthoringPlan `native_text` object must have at least one coverage entry; table cells, badge labels, chart labels and number+unit compositions must be traceable through stable synthetic text targets owned by their AuthoringPlan object.

Each entry records the formal text, canonical `text_spec_id`, concrete authoring
helper/path, TextFit measurement evidence and final output binding. Rich text
is measured as one phrase by default and carries ordered `run_ids`, per-run
text/style trace, content hashes and an explicit `measurement_scope`; an
explicit number+unit group must bind its number/unit runs. A helper must not
write formal text directly to the deck or manually add runs without this
content-bound measurement evidence.

Validate with:

```bash
python3 scripts/audit_text_coverage.py PROJECT/authoring-plan.json PROJECT/text-coverage.json \
  --text-fit-report PROJECT/text-fit-deck.json --json
```

Missing native-text coverage, missing measurement evidence, duplicate output binding, unknown owner or AuthoringPlan SHA mismatch are deterministic formal-text/provenance blockers. This auditor does not create SSIM, pixel or typography-similarity thresholds.

See `references/text-coverage-auditor.md` and `assets/text-coverage.template.json`.

## 8. Asset Generation

Generate every `imagegen_asset` as an independent asset with genuine RGBA alpha by calling the built-in native ImageGen tool. Record the prompt, reference, output and `native_imagegen_receipt` before authoring; if the receipt is missing, stop at the asset gate. Validate non-empty alpha bbox, transparent corners, safe padding, clipping and plausible subject coverage. For grids, detect actual row/column centers before slicing; repack by visible alpha bbox and visual centroid. For explicitly full-bleed ribbons/skyline bands, distinguish alpha-noise trim from bounded-asset QA, preserve the raw asset, record the derived transform and fit the derivative to the target physical aspect before using `contain`/`cover`.

For continuous low-frequency systems such as footer ribbons, skyline bands and header waves, rectangular alpha geometry is necessary but insufficient. Record a semantic parent bbox, sampled contour landmarks and child anchors. Compare the final composed region against the reference with `scripts/audit_continuous_band.py`; zero bbox delta must not close a visible contour mismatch. Keep readable footer/header text native and repair in this order: parent bbox -> contour profile -> asset scale/crop -> child anchors -> z-order.

Source crops are evidence, not silent final-asset fallback. Contact/sprite sheets are QA evidence and never final slide assets. If generation is unavailable or repeatedly fails, report the blocker or request an explicit fallback decision rather than substituting a low-quality scripted icon. An explicitly approved source-reuse fallback remains available for non-brand assets only. Brand-class final assets always require native ImageGen and its prompt, output, provenance, hash and tool receipt, even when an exact official source file is available. After export, run `scripts/validate_embedded_imagegen_assets.py` with the current request ID; every manifest `asset_id` must match an actual `ppt/media/*` byte hash. This closes the failure mode where a direct composer records ImageGen evidence but emits a deck with no pictures.

The source-visual coverage gate is upstream of visual closeout; a human crop
review cannot turn an omitted complex asset into a covered asset. Keep the
gate report beside the ImageGen manifest and bind both to the current source
hash.

## 9. Artifact Tool Build

Build a fresh editable PPTX through the strict repository `@oai/artifact-tool` authoring path. Preserve stable object IDs/names for selection-pane inspection and Repair Trace. Build component-local layers in container -> asset/icon -> text order, then audit physical z-order. Do not reopen/resave the authored deck through `python-pptx` as a repair path.

Artifact Tool Build must consume AuthoringPlan object IDs and implementation decisions. If a helper needs to deviate materially from the plan, record the deviation and revalidate the updated plan rather than silently changing the deck.

Complex visual systems may be one or a small number of semantic image assets when native fragmentation would reduce fidelity. Keep readable labels and ordinary semantic geometry native above/beside them.

Declare one coordinate space for the layout and keep it consistent across
`bbox` and `x/y/w/h` records. Validate it before build. Native tables also run
the cell-capacity/overlay-asset gate; a table that only passes aggregate
TextFit slots but has an invalid bbox, empty usable cell, unbreakable run or
text capacity overflow is not build-ready. The gate accepts the same
`fraction`/`normalized`/`px`/`pt`/`in` coordinate spaces as the layout
contract and reports density in physical points:

```bash
python3 scripts/validate_coordinate_space.py PROJECT/layout.json \
  --report PROJECT/coordinate-space-validation.json
python3 scripts/validate_table_layout.py PROJECT/layout.json \
  --report PROJECT/table-layout-validation.json
```

Charts remain native/editable when data are known. Missing future values stay blank and must never be serialized as zero.

## 10. Fresh PowerPoint Render

Use `scripts/render_authoritative.py`. Microsoft PowerPoint export is the final
visual authority. A verified LibreOffice+Poppler render with the task-local
authoring fonts is provisional diagnostic evidence only and cannot complete
final visual signoff. Record the actual renderer and the
`powerpoint-final-libreoffice-provisional` policy; use `--require-powerpoint`
for final acceptance. Artifact Tool
preview/import is structural evidence only. Do not
repair or rebuild a deck solely because that preview omits CJK glyphs when the
authoritative render and object audit are complete.

Render the exact current candidate after authoring and after every meaningful repair batch. Final evidence must link to the delivered PPTX hash. An old render cannot prove a new candidate.

## 11. Full-page Compare

Compare the fresh render with the immutable reference. Whole-page SSIM, pixel diff, balanced fidelity scores and regional metrics are diagnostic evidence only unless the user/project explicitly supplies a numeric target. A low visual metric creates repair work; it does not terminate production by itself.

## 12. Adaptive key Local Crops

Cut every candidate crop from the same final full-page render; never rerender per crop. In `fast`, inspect 3-5 highest-risk regions. In `strict`, inspect 5-10. If fewer material regions exist, inspect all of them. Prioritize dense text/cards, icon slots, charts, compact arrow+label components, bottom bars, circular centers, right-side tool panels and user-flagged areas.

Asset thumbnails are insufficient. Icon visibility, clipping, centering and z-order must be proven from the final PPT render crop.

Before Responsible Object Repair, run `scripts/text_render_feedback.py` against the immutable reference render and the fresh candidate render. Use its same-coordinate text crops to diagnose position, visible scale/weight and hierarchy drift. These tolerances are diagnostic only and never a whole-page release gate.\n\n## 13. Responsible Object Repair

Do not manually override contradictory evidence. A `repair_required=true` text-render record remains open until a fresh render clears it or an object-specific disposition records `resolved`/`false_positive_verified`, after-render evidence and a concrete review note. Generic prose such as “aligned” or “preserved” is not closeout evidence.

Every material mismatch must map to the responsible object/layer. Record page, crop/object IDs, mismatch, proposed delta, before evidence, after evidence, accepted/rejected state and reason. Prefer the 3-5 highest-impact defects in each iteration.

Repair the owning object instead of compensating through neighbors or chasing one scalar score. Protect already-correct regions. Pure placement defects should not trigger unnecessary ImageGen regeneration.

## 14. Re-render

Every accepted material repair requires a fresh render. Re-check the affected crop and the full page. Reject a local repair that materially regresses a protected crop or the whole page unless explicit human review establishes that the scalar regression is a renderer artifact and the visual/object evidence is better.

Before PASS, materialize `visual-closeout.json` from `assets/visual-closeout.template.json` and run `scripts/validate_visual_closeout.py` as specified in `references/visual-closeout-gate.md`. This is an evidence-consistency gate, not a scalar similarity threshold. Any unresolved material crop finding, unclosed text-render repair, missing structured region observation, or stale/mismatched final-render binding blocks PASS and returns to Responsible Object Repair.

In `fast`, retain the complete machine evidence and publish a compact summary
with `scripts/compact_acceptance_report.py`. Production `run_pipeline.py` and
`strict_reference_release.py` generate `compact-acceptance.json` automatically.
Run
`scripts/ppt_practical_lint.py` before delivery to report recurring PowerPoint
defects such as full-slide background shapes, unconfigured wide rounded
rectangles, unexpected effects and missing observed CJK typeface metadata.
Lint warnings create focused review work; they do not replace the final render.

## 15. Hard Correctness Check

Normal fixed-reference production has only these blocking categories:

1. `corrupt_or_unrenderable` — corrupt output or output cannot be rendered.
2. `formal_text_loss` — required readable/formal text is missing or materially altered.
3. `whole_slide_raster_fallback` — a whole-slide bitmap impersonates editability.
4. `required_editability_loss` — required native/editable objects are flattened or unavailable for editing.
5. `asset_missing_or_invalid_alpha` — required independent asset is missing, fake/empty alpha, clipped, or contaminated at the edge.
6. `severe_overflow_collision_oob` — severe overflow, collision or out-of-canvas geometry.
7. `semantic_table_misclassification` — list/card semantics are wrongly converted to a table, or a real table loses row/column semantics.
8. `chart_blank_serialized_as_zero` — unknown/blank chart values are fabricated as zero.
9. `source_or_provenance_mismatch` — source hash/provenance or required generated-asset provenance does not match the run.
10. `source_visual_asset_coverage_missing` — a source complex visual is not
    mapped to an independent final ImageGen asset.
11. `coordinate_space_mismatch` — layout units and object bboxes use different
    coordinate spaces or leave the declared canvas.
12. `table_cell_capacity_exceeded` — native table text cannot fit its actual
    usable cell after margins, overlays and declared row/column geometry.

Do not promote SSIM, regional SSIM, pixel score, bbox IoU, centroid drift, scale drift, icon similarity, text-fit utilization, five-dimensional A/B, report count or external comparator availability into production hard blockers.

Runtime/package checks may still fail closed when the required authoring environment itself is unavailable; they are environment prerequisites, not visual-fidelity acceptance gates.

Validate the final short-loop report with:

```bash
python3 scripts/validate_short_loop_run.py PROJECT/short-loop-run.json --root PROJECT --json
```

Use `assets/short-loop-run.template.json` as the compact report shape.

## 16. Final PPTX

Deliver only the candidate whose final PPTX/render hashes correspond to the accepted evidence and which has zero active hard blockers. Final acceptance requires current-source hash match, fresh full-page review, final local-crop review, exact formal-text ledger, object/editability inspection, independent asset alpha/provenance QA, semantic chart/table checks where applicable and Repair Trace for the last accepted material changes.

## Development regression, separate from production

Pixel / Text / Object / Icon-Asset / Local-Crop five-dimensional A/B remains valuable for skill development, benchmark replay and CI. It is not required for ordinary image-to-editable conversion and must not make normal delivery depend on any external comparator.

## Core fixed-reference implementation rules

- Use real font metrics and CJK-aware wrapping; preserve reference line topology. Reuse process-wide measurements across equal text/style/geometry slots; probe the maximum once for low-risk text and run binary or exact-topology search only when needed.
- Treat the text box as the intended editable slot, not the dark-pixel glyph bbox.
- Reserve explicit icon/arrow slots before fitting adjacent text.
- Use alpha-visible bbox plus visual centroid for transparent-asset placement when needed; preserve safe padding.
- Use content-aware grid cutting; reject declared/detected grid-count mismatch.
- Keep contact sheets out of final asset directories.
- Clear unintended shadow, glow, reflection and soft-edge effects when the reference is flat.
- Inspect physical PPTX layer order when icons/text disappear; object existence is not render proof.
- Use native filled arrows when the reference shows filled arrows; use continuous editable freeform/arc paths for compact loops/hooks when appropriate.
- Center cards/pills by geometry and vertical anchoring, not by baseline eyeballing.
- Preserve blank chart series as blank.
- Allow per-component geometry overrides when repeated content differs.
