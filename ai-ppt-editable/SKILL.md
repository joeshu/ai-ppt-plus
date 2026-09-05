---
name: ai-ppt-editable
description: Turn approved slide images, screenshots, rasterized PDF pages, image-slide intermediates, existing PPT/PPTX, or structured content into editable, rendered, technically validated PowerPoint. Trigger for “图片转可编辑PPTX/截图还原PPT/复刻版式/图标分层/文字提取/现有PPT修复”, reference reconstruction, native object authoring, or PPTX rendering and technical QA. It can run standalone or as the editable worker for $ai-ppt-plus. Do not use for whole-page image generation or deck-wide narrative/release; use $ai-ppt-visual-gen or $ai-ppt-plus.
metadata:
  package_revision: 2026.09.02.02
---

# AI PPT Editable

## Boundary and runtime

Create or repair editable PPTX while preserving the declared visual and text
authorities. This worker owns decomposition, object planning, authoring,
rendering, technical QA, and technical repair. It does not own narrative
redesign, deck-wide release, or human sign-off.

This skill is independently installable and invokable. Run commands from this
skill directory; its reconstruction scripts, references, templates, schemas,
font assets, pinned `requirements-ci.txt`, route contract, and tests are all
local. Validate this package and its standalone routing contract before work:

```bash
python3 scripts/validate_skill_package.py --skill-dir .
python3 scripts/validate_routing_contract.py
```

The reconstruction engine and shared QA contracts are byte-synchronized with
the pinned `完美第一版` snapshot of `joeshu/ai-ppt-plus`. Explicitly
documented post-baseline adapters extend that frozen core for portable resource
paths, font-directory precedence, native semantic objects and route-bound
quality evidence; they do not change the visual decomposition contract. Verify that source relationship before authoring:

```bash
python3 scripts/validate_perfect_sync.py
```

The exact source commit, file mapping, and intentional package-boundary or
post-baseline adapter exceptions are recorded in
`references/perfect-source-sync.md` and `assets/upstream-perfect-sync.json`.
The worker remains independently runnable;
when called by `ai-ppt-plus`, it consumes the orchestrator's approved handoff
and returns worker-level technical evidence. It never owns deck-wide narrative,
release eligibility, or human sign-off.

The split changes ownership and invocation only. Keep the checked-in
image-to-PPTX decomposition, asset extraction, composition, rendering, and QA
algorithms stable; any generality fix must be isolated, documented as an
explicit post-baseline adapter, and covered by a regression test.

## Authority model

In orchestrated mode, consume the immutable route decision, approved outline,
formal-text authority, design revision, reference roster, editability target,
and worker manifests supplied by `$ai-ppt-plus`. The pinned reconstruction
baseline intentionally uses the same mutually exclusive `route-decision/v1`
routes as `完美第一版`: `visual-creation` and
`reference-reconstruction`. A post-baseline native-authoring route is an
orchestrator extension, not a replacement for this worker's synchronized
reconstruction contract.

In standalone mode:

- the supplied reference is visual authority unless the user asks for redesign;
- user-provided copy is formal authority;
- OCR/vision transcription is proposed text with confidence/uncertainty, not an
  unquestioned fact source;
- missing brand assets, chart data, or illegible text are blockers or explicit
  placeholders, never invention.

Read `references/perfect-replica-practice.md`,
`references/case-intake-protocol.md`,
`references/image-to-editable-ppt-contract.md`,
`references/reference-fidelity-audit.md`,
`references/three-round-distillation-methodology.md`,
`references/automatic-distillation.md`,
`references/automatic-training-driver.md`,
`references/candidate-repair-protocol.md`,
`references/source-crop-integrity.md`,
`references/training-data-protocol.md`,
`references/reconstruction-contract.md`,
`references/editability-levels.md`, `references/native-object-protocol.md`, and
the asset/text/chart protocols relevant to the page.
For last-mile viewer compatibility and preservation, also read
`references/ooxml-compatibility.md`.
For the mandatory final visual-asset route, also read
`references/imagegen-final-asset-policy.md`.
For the five post-baseline contracts and their shared adapter, also read
`references/perfect-first-extensions.md` and use
`scripts/perfect_first_adapter.py`; do not replace the synchronized core with
a simplified reconstruction path.

For every reference-led page, build and validate a
`reference-fidelity/v1` manifest with `scripts/validate_reference_fidelity.py
--strict`. It is a hard pre-composition and post-render gate for one-to-one
icon provenance, exact native text/style evidence, gradient treatment and
aspect-ratio mapping. Generic symbols, missing source bboxes, sentinel `1×1`
boxes, unresolved object IDs, stale source/candidate hashes, silent flat-fill
fallbacks, and undeclared 3:2-to-16:9 stretching block the page. A technical
pass remains `accept-for-human-review` until visual fidelity, formal text and
editability are confirmed by a person.

## E0 — Intake, isolation, and preflight

1. Preserve originals and create a unique run root. Record source hashes and
   page-to-reference mapping; never overwrite a baseline or input deck.
2. Normalize only derived comparison/render copies. The original remains
   authoritative and keeps its own hash.
3. Probe authoring/render/font/OCR capabilities and validate the selected
   backend binding. For CJK, validate the task-local font and rendering evidence.
   When embedding fonts, the declared run family and the font's internal family
   must match exactly or through an explicit, audited alias map; unknown family
   mismatches are blockers. Record the resolved family and alias in the font
   report.
4. Persist route and formal-text authority. A blocked or undecided route cannot
   enter composition.

## E1 — Inventory and object plan

For every page, inventory visible content independently: background, frame,
panels, text boxes/runs, charts, tables, icons, logos, decorations,
illustrations, artistic typography, and page furniture. Record source bbox,
layer, z-order, anchor, editability level, replaceability, and provenance.

Choose the highest practical editability level without mislabeling:

- native text, shapes, groups, tables, and charts where semantics/data are known;
- native shapes/groups for simple cards, panels, dividers, process nodes and
  table grids; each semantic container has its own object ID;
- movable raster/vector assets for icons, illustrations, and complex artwork;
- a whole-page bitmap only as an explicitly image-only fallback, never as an
  editable reconstruction.

Repeated semantic panels remain independently movable. Simple semantic panels,
cards, frames and tables are native by default. A text-free complex visual
substrate may remain an independent image only when its manifest records the
exception; it never replaces native text or a table object.

## E2 — Reference decomposition

For fixed-reference reconstruction, preserve page ratio, layout, hierarchy,
spatial relationships, palette, and visible styling. Separate:

1. background texture/photography;
2. native frame/skeleton shapes/groups for simple geometry, or a text-free
   traceable complex visual substrate when native recreation would reduce
   fidelity;
3. icons, decoration, logos, illustrations, and artistic words;
4. editable formal text;
5. native charts/tables with their own data/representation authority;

When the corresponding evidence exists, the perfect-first extension boundary
is mandatory: verified chart records may be promoted to native charts; simple
gradients may remain native while complex B2/B3/B4 gradients stay traceable
assets; canonical font aliases and nested run styles must survive composition;
object manifests must carry geometry for object-level acceptance; and
human-confirmed cases may be ingested automatically only after explicit
approval. `compose_pptx.py` runs the shared adapter before the frozen backend,
and `run_pipeline.py` runs its contract preflight.

The authoring boundary accepts both legacy flat text records and the canonical
nested `text-layout-manifest` form. In the latter, `bbox` supplies geometry,
`content` supplies immutable copy, `style` supplies the base font metrics, and
each run's nested `style` supplies local color/weight/size overrides. Never
flatten runs before composition: a manifest can validate successfully while
still losing brand colors if the authoring adapter only reads flat fields.

For native rich-text authoring, apply the shape-level base style before
writing `runs[]`, then write the runs once and do not reapply a whole-shape
font/color style afterward. Reapplying the base style after runs silently
overwrites local emphasis while leaving the text object technically editable.
The P0 gate must therefore verify both the canonical manifest and the final
OOXML `a:r`/run-level properties, followed by a rendered comparison.

Use `references/icon-asset-protocol.md` and `references/imagegen-sheet-slicing.md` for B4/B5 provenance, sheet slicing and cutout QA,
`references/panel-asset-protocol.md` for independent panels,
`references/text-style-protocol.md` for mixed color/weight/line breaks, and
`references/chart-reconstruction.md` for every chart. A source crop is valid
only with bbox and source hash; missing assets use the declared generation
route and remain independent assets after extraction. For icons, gradient
visuals and complex artistic elements, the route is native `imagegen` by
default; if generation fails, pause and ask the user to choose exactly one:
continue/retry native imagegen, or use original-image crop/cutout
(`source_reuse`). Never make that choice implicitly. Record the explicit user
decision, reason and timestamp in the asset manifest; an undecided asset is
blocked. For `source_reuse` crops,
the delivered-file hash alone is insufficient: record `source_crop_policy` and
the canonical RGBA `source_crop_sha256`, then run
`validate_source_crop_integrity.py`. For icons, gradient visuals and complex
artistic elements, source crops are reference/QA evidence only and never the
delivered final asset: those classes must use native `imagegen` and remain
independent assets. Run `validate_imagegen_final_assets.py --strict` before
composition and after the final render. Exact crops must
match the declared source bbox pixel-for-pixel; derived crops must explicitly
declare their alpha/processing step. This prevents a neighboring crop from
passing merely because its metadata and file hash are internally consistent.

Run the reference-fidelity asset-boundary subgate after the contact sheet and
after the final render. It must check for neighboring text/separators/header
bands inside each icon crop, unintended matte rectangles on decorative art,
replayable pixel bboxes for source reuse, and an effect-layer inventory for
complex artwork. Hash/visibility/object-count passes do not waive these checks.
If a complex visual contains glow, volume gradients, connector arrows, rings,
shadows or brush/wave edges, preserve or explicitly account for each effect;
flat editable substitutes must be marked as bounded degradation rather than
accepted as a faithful pass.

Do not use deck-wide visual generation to redesign an approved fixed reference.
Instead, invoke native imagegen as a scoped element-generation event for every
icon, gradient visual, complex illustration, decorative art or artistic-
typography asset. This is mandatory even when a source crop exists; source
reuse is reference evidence only unless the user explicitly approves the
fallback above. If generation fails, invoke that user-decision gate—never
silently fall back to the source crop, a generic symbol or a flat fill. Official
brand marks remain authorized-source assets
under the brand exception.

For every reference-led page, run the final-imagegen-asset gate before
composition and again after the final render. In addition, run the
cross-manifest gate below:

```bash
python3 scripts/validate_reference_fidelity.py reference-fidelity.json \
  --strict --require-imagegen \
  --icon-generation-manifest icon-generation-manifest.json \
  --icon-assets-manifest icon-asset-manifest.json \
  --imagegen-assets-manifest imagegen-assets-manifest.json \
  --render-report render-report.json
```

The generation manifest is not a status note: every family must enumerate
`asset_ids`, `generated_asset_paths`, and `legacy_replaced_asset_ids`. The gate
must resolve each ID to the same delivered file in all three manifests, inspect
the actual PNG alpha channel, require per-icon split evidence, reject a sprite
sheet or stale source-reuse record, and reject an unresolved reference object.
Do not omit `--require-imagegen` for icon, gradient-visual or complex-art
records. The ordinary source/hash and boundary checks remain required for the
reference evidence and official brand exception.

Never assume a generated asset sheet is a uniform grid. Before B5, inspect
alpha row/column spans and classify the sheet as `uniform_grid`, `variable_row`,
or `artistic_row`. Fixed `4x4` slicing is permitted only after uniform-grid
evidence is recorded; variable-row sheets require row-aware explicit crops,
and complex artistic typography requires one full-row asset per visual line.
Contact-sheet review must reject clipped glyphs, edge-touching circles, merged
neighboring objects, or an art row split into character fragments. See
`references/imagegen-sheet-slicing.md`.

For image-led improvements, run the three-round protocol: visual diagnostic,
semantic-panel decomposition, then native-text/object distillation. Preserve
the visual-best and editable-best candidates as separate evidence, and use the
actual panel manifest count rather than a hand-count when configuring gates.
The image-to-editable contract is a hard gate: a complex正文 panel may retain
only a text-free substrate as an independent asset; formal text must be native
text objects with resolvable `text_layer_ids`. A raster panel that lacks
`raster_text_audit` evidence, contains formal text, or uses a flattened full
slide blocks delivery.

For repeated improvement runs, use `scripts/distillation_loop.py`: score the
existing reports, classify feedback by owning layer, gate the candidate against
the previous baseline, and record hash-bound cases. A technical acceptance is
only `accept-for-human-review`; never treat it as automatic release or model
training approval. Only human-approved, fresh, non-flattened cases may enter a
later retrieval or supervised-training export.
Use `scripts/candidate_controller.py` to generate isolated, region-scoped repair
proposals and rank only gated candidates. Candidate plans are opt-in and must
not overwrite the previous baseline; stop automatic repair after three rounds
or at the first new blocker.
After a person confirms visual fidelity, formal content, and editability, use
`scripts/training_export.py approve-case` followed by `export`. The exporter
must reject stale hashes, duplicates, incomplete approvals, and unreviewed
cases; it prepares retrieval data but does not claim that model weights were
trained. Use `scripts/run_training_cycle.py` as the automation boundary from
GitHub Actions or another trusted scheduler. It records skipped,
waiting-for-approval, prepared, blocked, and trained-candidate states. A
trained candidate remains pending human evaluation and promotion; the driver
does not invent a trainer, GPU, checkpoint registry, or release approval.

For any post-composition compatibility repair, use only the ZIP-level
`scripts/normalize_ooxml_relationships.py` adapter. Never reopen and resave the
authored deck through `python-pptx` after rich text, independent assets, or
gradients have been composed. Run
`scripts/validate_repackaging_invariants.py` and block delivery if the slide
part set, media bytes, picture count, text-run/style digest, or gradient count
changes. This is a technical preservation gate; the repaired file still needs
rendered visual comparison and human review.
When no GPU is available, let the driver build the CPU-only retrieval index
with `scripts/build_retrieval_index.py`. Treat it as retrieval enhancement and
split-leakage evaluation, not as semantic vision-model training or weight
更新.

## E3 — Author editable objects

1. Build/update the canonical slide-object manifest before composition.
2. Use the checked-in authoring adapter and shared scripts. Bind every object to
   source evidence, text authority, or an explicit generated-asset record.
3. Keep text as real text boxes/runs with stable line breaks, emphasis, and
   font evidence. Never copy pseudo-text from a generated image into formal copy.
4. Keep charts native only when source data is verified; otherwise use the
   declared hybrid/static representation and preserve labels as native text.
5. Keep PPTX and preview drawing order equivalent so technical previews are
   meaningful.
6. For reference reconstruction, compose simple semantic panels/cards as
   native shapes or groups and verified tables as native PowerPoint tables.
   Preserve complex gradients, illustrations, icons and textures as independent
   visual assets; do not trade their fidelity for a generic editable substitute.
6. Treat an adapter preview with missing CJK glyphs as a renderer diagnostic,
   not as permission to rasterize text. Embed the task-local font, render the
   exact embedded PPTX with the release renderer, and require preview/final
   render consistency plus native-text object evidence before delivery.

For native chart promotion, pass `--chart-manifest` to the composer or let the
pipeline validate the project manifest. Never promote `unverified` chart data;
the adapter rejects a non-native chart that would otherwise be silently
rendered by the native chart primitive. Adapter, typography, gradient, and
object-audit reports are evidence, not human sign-off.

## E4 — Render and validate

Render every page and run structural, object, asset-hash, font, text-layout,
overflow, overlap, panel, chart, route, and preview-consistency gates applicable
to the project. Run `semantic_object_audit.py` with the final object manifest,
text manifest, `--require-source-hashes`, and
`--require-independent-text-manifest`; `inspect_editable_objects.py` alone is
not a completeness gate because it can prove the declared objects while still
missing undeclared shapes in the deck. Compare against the authoritative
reference when one exists. Review both a deck strip and full-resolution pages.

For strict object acceptance, run
`inspect_editable_objects.py --require-types --require-geometry
--require-complete-manifest`; geometry is compared in normalized slide
coordinates with a declared tolerance, and every final shape must be present in
the object manifest. A passing pixel score does not waive a type, geometry,
gradient, font, chart provenance, or source-hash failure.

Automated checks are technical evidence. Record `human_visual_review_required`
when applicable and never synthesize approval metadata.

For every fixed-reference page, run the last-mile visual lock after composition
and after the final render:

```bash
python3 scripts/validate_visual_lock.py PROJECT/visual-lock.json \\
  --report PROJECT/qa/visual-lock.json --strict
```

The lock is a hard technical gate for critical text visibility and exact-once
copy, semantic container assignment, non-empty title/callout/footer regions,
icon style-anchor evidence, typography deltas, critical-region scores and
unapproved additions. A technically present text object does not pass when it
renders in the wrong band, in a duplicate box, behind an empty source
container, or outside the declared reading structure. A generated icon does
not pass merely because its meaning is similar; its source-locked silhouette,
container shape, palette and shadow policy must be reviewed in the final render.

## E5 — Repair and handoff

Repair the owning object or asset, not the symptom. Re-render and rerun affected
gates after every patch. Do not change narrative, formal facts, or the approved
reference design to make a validator pass. Return:

- editable PPTX and rendered previews;
- canonical object/content/asset manifests and hashes;
- technical validation reports and unresolved blockers;
- changed slide list, editability summary, and worker handoff.

In standalone mode, label delivery as worker-level technical completion. In
orchestrated mode, return to `$ai-ppt-plus`; only the orchestrator can aggregate
deck-wide evidence and determine release eligibility.

## P0 — Executable fidelity gates

For a fixed-reference page, keep `source-inventory.json`, the canonical
`page-graph.json`, the reference bytes and the final PPTX in one evidence
chain. The source inventory must come from an independent observation
(`method: source-image-observation`) and use an observation ID different from
the graph's planning observation ID. Run the three-way check after composition
and after the actual PPTX has been rendered:

```bash
python3 scripts/validate_source_coverage.py \
  --reference reference.png \
  --inventory source-inventory.json \
  --page-graph page-graph.json \
  --deck candidate.pptx \
  --report source-coverage-validation.json
```

The gate checks reference SHA-256, source-to-graph bindings, final object IDs,
native object types and exact formal text. For multi-page route rosters, the
pipeline persists an ordered run-local page manifest instead of guessing page
order. Under the root-P0 or release profile, missing coverage evidence or
missing reference pages blocks the run and is forwarded into the project gate
and report index.

Use `scripts/run_p0_repairs.py` for a one-page bounded repair batch. It solves
only explicit graph relations, preserves locked geometry, calibrates typography
through the real LibreOffice/PDF renderer, and accepts generated assets only
when native-imagegen provenance, alpha QA and silhouette IoU evidence agree.
Its output remains `pending-visual-review`; technical evidence never silently
becomes human visual approval. The quality gate also rejects strings, booleans,
NaN, infinity and out-of-range similarity metrics without throwing a runtime
exception.

## Blocking conditions

- missing formal-text or visual authority;
- whole-page bitmap presented as editable output;
- rasterized simple card/panel/frame/table where a native semantic object is
  required;
- complex正文/card/panel raster containing formal text, or missing
  `raster_text_audit` and native `text_layer_ids` evidence;
- icon/panel/chart/text objects missing provenance or required independence;
- source/reference hashes drifted after planning;
- font, render, overflow, overlap, or package blockers remain;
- technical pass represented as human approval;
- reconstruction redesigns the approved reference without explicit user scope;
- last-mile visual lock reports missing/duplicated formal text, empty semantic
  containers, wrong text-to-container assignment, undeclared banners/shadows,
  icon style mismatch, typography deviation over 12%, or critical-region score
  below the declared threshold.

After human confirmation, `scripts/ingest_approved_case.py` or the scheduled
`scripts/run_training_cycle.py` may export the fresh case to the hash-bound
dataset and CPU retrieval index. Model training and weight promotion remain
separate external stages and require independent evaluation.


## Native structure enforcement for image reconstruction

For every reference-reconstruction or editable-PPTX run, the frame/skeleton
image is geometry evidence only. It must never be emitted as a semantic
full-slide or panel layer. Before composition, create explicit native
semantics for every recoverable simple card, panel, divider, connector and
table:

- simple boxes, bands, lines, arrows and repeated panels use native shapes or
  native groups;
- recoverable grid data uses native PowerPoint tables, with explicit
  `rows`, `columns`, `merges`, `data_source`, and `data_snapshot`;
- formal text remains native text or table-cell rich text;
- icons, logos, complex gradients and complex illustrations remain separate
  assets and must not carry formal text or table data.

The input manifest must declare `native_panels` and `native_tables` whenever
those structures are present. A native-required object cannot provide a raster
`file` as its implementation. Invoke composition with the native-structure
requirement for reference reconstruction, and block delivery when the final
PPTX has a semantic full-slide frame picture, a raster native-required panel,
missing native tables, or formal text inside a raster asset.

For a source containing a green-screen frame plus separate text boxes, use the
text boxes as formal-content evidence and map them into the object manifest by
stable IDs; do not OCR the same text again unless the source text is absent.
The acceptance test must include a mutation smoke test: edit a table cell and
move a panel/group, then render and confirm the expected regions change.


<!-- unattended-distillation:entrypoint -->
## Unattended distillation integration

This worker can be checked by the root unattended distillation controller, but it does not self-promote visual or semantic changes. The controller may restore only the checked-in native-structure and text/visual policy blocks. Native table/object evidence, source hashes, rendered comparison, formal-text fidelity and human-review requirements remain hard gates; a passing technical repair is not a human sign-off.
<!-- /unattended-distillation:entrypoint -->
<!-- unattended-distillation:improvement-proof -->
## Improvement proof requirement

The editable worker must not claim that a semantic panel or table became editable from a generic test pass. Any unattended native-structure or text/visual repair requires the corresponding case replay, native-object evidence, mutation smoke test and rendered comparison; missing replay evidence stops promotion.
<!-- /unattended-distillation:improvement-proof -->

<!-- unattended-distillation:case-replay -->
## Case-level replay requirement

For every native table/panel or text-visual repair, rerun the actual reconstruction case after the change. A candidate must carry source and deck hashes, rendered comparison, OOXML `a:tbl` evidence, merge topology, native text/run audit and mutation smoke-test evidence; a unit-test pass alone cannot establish editability.

When the reference and the final render are authored slide canvases (rather
than viewer screenshots with black bars), run `compare_visual.py --raw-slide`;
otherwise the viewer-crop heuristic can report a false visual blocker. Use
`case_replay_audit.py` as the case-level hard gate: it checks real PowerPoint
table objects, exact OOXML `<a:tbl>` elements, declared merge topology,
rich-text runs, native formal text, and full-slide-picture absence. Count the
actual `<a:tbl>` element, not the prefix shared by `<a:tblPr>` and
`<a:tblGrid>`. Keep its report beside the baseline/candidate evidence and
rerun the mutation smoke after every repair.
<!-- /unattended-distillation:case-replay -->


## Distillation case matrix

A single integrated replay case is a golden anchor, not full skill coverage. The checked-in matrix at `evals/distillation-case-matrix.json` separates atomic contract cases from actual PPTX replay cases across P0 routing/package safety, P1 native structure and visual fidelity, and P2 full-deck/cache consistency.

Targeted failure runs select the direct responsibility, adjacent responsibilities, and all P0 safety cases. Pre-merge, nightly, and manual full evaluations select the complete matrix. Every replay candidate must emit baseline, candidate, improvement, object, visual, and mutation evidence; unit-test success alone is insufficient.

The current social case is marked `static_sentinel`: it verifies that the replay/audit machinery can run, but it cannot promote a distilled repair. A real candidate must be regenerated after the repair and bound to that repair's fingerprint. The validator reports replay coverage debt, and the unattended controller blocks promotion when the affected category has no actual replay evidence.
