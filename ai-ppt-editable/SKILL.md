---
name: ai-ppt-editable
description: Turn approved slide images, screenshots, rasterized PDF pages, image-slide intermediates, existing PPT/PPTX, or structured content into editable, rendered PowerPoint. Trigger for 图片转可编辑PPTX、截图还原PPT、复刻版式、图标分层、文字提取、现有PPT修复. It can run standalone or as the editable worker for $ai-ppt-plus.
metadata:
  package_revision: 2026.09.20.13
---

# AI PPT Editable

## Mission

Reconstruct or repair editable PPTX with the supplied reference as visual authority and user-provided copy as formal-text authority. For fixed-reference work, visual fidelity is determined from the fresh final render, not from process paperwork or a scalar score.

New strict reconstruction uses JavaScript ESM with `@oai/artifact-tool`. Python is inspection/QA only and is not an authoring fallback. Whole-page raster fallback is forbidden.

Read `references/knight-short-loop.md` for the normative production contract. Read `references/authoring-plan.md` for the pre-build execution contract. Read `references/text-coverage-auditor.md` for formal-text producer coverage. Read `references/geometry-primitive-resolver.md` for pre-build geometry selection and parameter binding. Read `references/asset-render-coordinate-loop.md` for B5 alpha-space/slot/render-space evidence and continuous-band contour evidence, and `references/protected-repair-planner.md` for B6 constrained repair batches. `references/knight-fidelity-port.md` remains implementation guidance. External Knight A/B is a development/evaluation workflow, not a runtime dependency.

## Formal production chain

For normal fixed-reference reconstruction run this chain and no additional visual release-gate chain:

`Reference -> Visual Inventory -> AuthoringPlan -> Geometry Primitive Resolution -> native_editable/imagegen_asset -> Text Slot Preflight -> Text Coverage Audit -> Asset Generation -> Artifact Tool Build -> Fresh PowerPoint Render -> Full-page Compare -> 5-10 key Local Crops -> Responsible Object Repair -> Re-render -> Hard Correctness Check -> Final PPTX`

PageGraph, TextGraph, ChartGraph, manifests, SSIM, pixel diff, five-dimensional A/B and other metrics may support diagnosis, traceability and regression analysis. They do not replace looking at the fresh render and do not independently block a visually repairable page.

## 1. Reference

Freeze source path/page, dimensions, aspect ratio and SHA-256. Historical PPTX, renders, PageGraphs or crops cannot satisfy a new run. The current source is immutable visual authority unless the user explicitly requests redesign.

## 2. Visual Inventory

Inventory visible text, cards/panels, repeated components, semantic tables, charts, arrows/connectors, icons/logos, decorations and complex art. Assign stable object IDs and approximate source bboxes. The inventory exists to support authoring and responsible-object repair, not to become a separate visual gate.

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

All brand-class visuals use the native ImageGen route. This includes `logo`,
`brand`, `brand_lockup`, `wordmark`, `calligraphic_slogan`, `signature`,
`seal`, `brand_band`, `5g_mark` and `locked_brand_art`. A source crop may guide
the prompt and provide geometry/color evidence, but it is never a final brand
asset and it is never silently cut out or reused. Generate each brand visual as
one independent transparent asset when it overlays the slide; preserve a
complete lockup as one generated asset rather than OCR/retypesetting its
internal lettering. The resulting PPT picture remains movable and replaceable.

Keep readable formal text native. Keep independent visual assets independently movable. Editability is semantic editability, not maximum object fragmentation.

Do not infer a table from borders, repeated rows or two-column alignment. A table requires real field/record/cell semantics. Icon+title+description repetitions remain repeated editable components.

## 6. Text Slot Preflight

Measure every visible native text path before authoring. Determine the true editable slot, preserve reference line count and role hierarchy, and use the same runtime-resolved font for fit and authoring. Chinese runs must set Latin/East-Asian/complex-script OOXML typeface metadata as required by the runtime contract.

When text does not fit, repair in this order: text-slot bbox -> margins -> divider/icon reservation -> intended wrapping/line spacing -> role-consistent font adjustment. Do not shrink first. Repeated cards may use component-local divider positions, body widths, icon slots and font scales when the reference differs.

The TextFit Core contract in `references/knight-fidelity-port.md` defines the
measurement/report details: CJK character wrapping, intact Latin/number/unit
runs (including symbol-leading values such as `-12.5%`), explicit reference
line-count locking, target-size box deficit evidence and the
`text_slot_first_font_shrink_last` repair policy. `reference_scale` is review
evidence only; it is not a universal numeric release gate.

## 7. Text Coverage Audit

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

Generate every `imagegen_asset` as an independent asset with genuine RGBA alpha. Validate non-empty alpha bbox, transparent corners, safe padding, clipping and plausible subject coverage. For grids, detect actual row/column centers before slicing; repack by visible alpha bbox and visual centroid.

For continuous low-frequency systems such as footer ribbons, skyline bands and header waves, rectangular alpha geometry is necessary but insufficient. Record a semantic parent bbox, sampled contour landmarks and child anchors. Compare the final composed region against the reference with `scripts/audit_continuous_band.py`; zero bbox delta must not close a visible contour mismatch. Keep readable footer/header text native and repair in this order: parent bbox -> contour profile -> asset scale/crop -> child anchors -> z-order.

Source crops are evidence, not silent final-asset fallback. Contact/sprite sheets are QA evidence and never final slide assets. If generation is unavailable or repeatedly fails, report the blocker or request an explicit fallback decision rather than substituting a low-quality scripted icon. An explicitly approved source-reuse fallback remains available for non-brand assets only; brand assets remain blocked until native ImageGen succeeds.

## 9. Artifact Tool Build

Build a fresh editable PPTX through the strict repository `@oai/artifact-tool` authoring path. Preserve stable object IDs/names for selection-pane inspection and Repair Trace. Build component-local layers in container -> asset/icon -> text order, then audit physical z-order. Do not reopen/resave the authored deck through `python-pptx` as a repair path.

Artifact Tool Build must consume AuthoringPlan object IDs and implementation decisions. If a helper needs to deviate materially from the plan, record the deviation and revalidate the updated plan rather than silently changing the deck.

Complex visual systems may be one or a small number of semantic image assets when native fragmentation would reduce fidelity. Keep readable labels and ordinary semantic geometry native above/beside them.

Charts remain native/editable when data are known. Missing future values stay blank and must never be serialized as zero.

## 10. Fresh PowerPoint Render

Render the exact current candidate after authoring and after every meaningful repair batch. Final evidence must link to the delivered PPTX hash. An old render cannot prove a new candidate.

## 11. Full-page Compare

Compare the fresh render with the immutable reference. Whole-page SSIM, pixel diff, balanced fidelity scores and regional metrics are diagnostic evidence only unless the user/project explicitly supplies a numeric target. A low visual metric creates repair work; it does not terminate production by itself.

## 12. 5-10 key Local Crops

For each page inspect 5-10 same-coordinate reference/candidate crops, prioritizing the most material regions: dense text/cards, icon slots, charts, compact arrow+label components, bottom bars, circular centers, right-side tool panels and user-flagged areas. If a page genuinely has fewer than five material regions, inspect all of them.

Asset thumbnails are insufficient. Icon visibility, clipping, centering and z-order must be proven from the final PPT render crop.

## 13. Responsible Object Repair

Every material mismatch must map to the responsible object/layer. Record page, crop/object IDs, mismatch, proposed delta, before evidence, after evidence, accepted/rejected state and reason. Prefer the 3-5 highest-impact defects in each iteration.

Repair the owning object instead of compensating through neighbors or chasing one scalar score. Protect already-correct regions. Pure placement defects should not trigger unnecessary ImageGen regeneration.

## 14. Re-render

Every accepted material repair requires a fresh render. Re-check the affected crop and the full page. Reject a local repair that materially regresses a protected crop or the whole page unless explicit human review establishes that the scalar regression is a renderer artifact and the visual/object evidence is better.

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

Pixel / Text / Object / Icon-Asset / Local-Crop five-dimensional A/B remains valuable for skill development, benchmark replay and CI. It is not required for ordinary image-to-editable conversion and must not make normal delivery depend on Knight or another external comparator.

## Core implementation rules retained from Knight study

- Use real font metrics and CJK-aware wrapping; preserve reference line topology.
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
