---
name: ai-ppt-plus
description: Turn PDF, DOCX, Markdown, Excel/CSV, project files, meeting notes, images, existing PPT/PPTX, or approved outlines into narrative-coherent, visually consistent, editable, renderable, quality-checked PowerPoint deliverables. Trigger for “做PPT/幻灯片/演示稿/路演稿/汇报材料”, outline-first deck planning, image-model-generated high-end visual-intermediate design, slide reconstruction, PPTX redesign/inspection/repair, or resuming a multi-session deck. Outputs structured briefs, source inventories, outline tables, design systems, generated visual drafts, manifests, editable PPTX, validation and delivery reports. Do not trigger for a prose-only summary, a standalone image, spreadsheet-only analysis, or image-to-PPT reconstruction when the dedicated reconstruction skill is the narrower fit.
---

# AI PPT Plus

## Goal and boundaries

Build decks through explicit artifacts and gates: sources → structured outline → user approval → design system → visual intermediate → editable PPTX → render/validate → repair → human closeout. Never treat a generated slide image as the formal text source or as sufficient editable delivery.

Use for new decks, reference-led decks, outline-only or visual-only work, PPT/PPTX redesign, inspection, repair, charts, and multi-session projects. Exclude unrelated document writing, generic image generation, and tasks whose only goal is pixel-faithful image reconstruction; route the latter to `reconstruct-editable-pptx`.

## Start-up checks

1. Run `scripts/probe_environment.py --output environment-report.json` and `scripts/probe_fonts.py --output font-report.json --font-dir project-fonts/` before choosing a backend. For Chinese decks, copy the bundled `assets/fonts/NotoSansCJKsc-Regular.otf` and `font-manifest.json` into the task's `project-fonts/` unless the user supplies a licensed font. Read `references/font-portability.md` and `references/wps-compatibility.md`: use Microsoft YaHei only when already licensed and locally available; never redistribute it. Pass the same task-local font directory to `render_pptx.py --font-dir`. Run `scripts/validate_font_asset.py --font-dir project-fonts/ --require-cjk` to verify the declared asset before authoring. Chinese delivery remains blocked unless `declared_font`, `resolved_font` and `render_visible` all pass, target-device review is recorded, and (when requested) `inspect_pptx.py` verifies embedded-font relationships; a sidecar font is not the same as an embedded font. Use `delivery_check.py --require-embedded-fonts` for a strict embedded-font delivery. If the authoring backend cannot embed fonts, record `embedding: unsupported` and stop final delivery unless the user explicitly accepts it. Never write commands/tools as though they exist without this evidence.
2. Read `references/source-intake.md`; inventory every source and record readability, authority, conflicts, missing facts, OCR needs, and sensitive-data signals.
3. Establish goal, audience, setting, language, page/time limit, deadline, output format, editability, formal data, brand/font rules, original assets, outline and references. Do not invent missing critical inputs.
4. Classify the task: text-only; text+references; reference-only reconstruction; existing deck redesign; PPTX inspection/repair; data chart; complex visual; incomplete input; outline-only; visual-only. Choose one mutually exclusive visual route: `visual-creation` when no approved fixed reference governs the page, or `reference-reconstruction` when a user/approved reference image governs the page. Before downstream work, persist `route-decision.json` from `assets/route-decision.template.json` (or the visual-creation template) and run `scripts/validate_route.py`; do not infer the route from a filename or from whether an image happens to exist.
5. Create or restore `deck-brief.md`, state, source inventory, outline, design system, asset/slide manifests, issue log, validation and delivery records. Create `report-index.json` for the project reports and produce `project-report.json` with the unified report envelope. Chat history is not authoritative state.
6. On resume or branch creation, run `scripts/validate_handoff.py handoff.json`. A missing artifact, missing required handoff field, PPTX hash mismatch, delivered state with blockers, or delivered state with remaining slides is a blocker; do not continue from chat memory.
7. When accepting a regression case as a baseline, use `scripts/revision_guard.py freeze` to archive the exact PPTX, source/reference, rendered preview, manifests and quality reports with SHA-256 evidence. The operation must not overwrite an existing archive. Record excluded experiments and known open issues; every later repair creates a new revision. Read `references/regression-revision-contract.md`.

## Routing

- Outline-only: stop after approved `outline.csv|xlsx` and narrative report.
- Visual-only: require approved outline or explicit visual brief; stop after reviewed visual manifest.
- Reference-only reconstruction: require formal text or mark text as transcription needing confirmation; preserve layout, do not redesign; use the approved reference as visual authority and do not invoke whole-page visual creation merely to satisfy a different route. The B4 asset-extraction route is mandatory for every icon, decoration and artistic word in a reference reconstruction: use ChatGPT imagegen to generate the frame-excluded asset sheet, even when an original asset is available. An original asset may be supplied as the edit target/reference, but it must not bypass imagegen, B5 cutout/split QA or the imagegen evidence manifest; this route must not redesign the slide.
- Existing PPTX inspection/repair: inspect before mutation; preserve the original; render, diagnose, patch, and revalidate.
- Chart task: require traceable data and units; prefer editable chart or linked/reproducible data.
- Complex illustration: generate/extract only if provenance and fidelity are acceptable; otherwise place an explicit, documented placeholder.
- Incomplete critical input or unresolved conflict: move to `revision-required`, offer no more than three concrete choices, recommend one, and wait.

Read `references/narrative-strategy.md` for story decisions, `references/artifact-ownership.md` for authority/conflict rules, and `references/icon-asset-protocol.md` whenever a page contains icons, decorations, logos, illustrations or decorative typography.
For reference reconstruction with visible text styling, also read `references/text-style-protocol.md` and run `scripts/validate_text_style_map.py`; this is the reusable gate for preserving mixed-color text, emphasized numbers, line breaks and text-box boundaries.
For repeated cards or bordered content modules, also read `references/panel-asset-protocol.md` and run `scripts/validate_panel_assets.py --require-independent`; each semantic panel must remain independently movable.
Record every case-specific workaround in the issue log with its trigger, why the normal path failed, scope, validation evidence and rollback/expiry condition. Promote it into the shared toolchain only when the failure is reproducible across references; otherwise keep it as a documented special attempt.
Before visual comparison, run `scripts/reference_audit.py REFERENCE CANDIDATE`; distinguish viewer screenshot letterboxing/black bars from actual slide content, and compare at the same aspect ratio and render scale.

Use `regions[]` and `objects[]` for repeated visual modules; never encode a
fixed number such as six panels into the general workflow. Record movement,
content and component editability separately. A complete logo mark/wordmark
uses the `brand_lockup` asset policy and remains one authoritative movable
asset; do not OCR it into ordinary editable text unless the user asks for a
redesigned or component-editable logo. The six-panel R13 case is a regression
fixture only.

After slide, object and asset manifests are generated, build
`manifest-registry.json` as the canonical cross-manifest index. It unifies
page/region/object/asset IDs, provenance and the final PPTX SHA-256, while
leaving each domain manifest authoritative for its own fields. Validate it
before project or delivery checks with `scripts/manifest_registry.py`; use
`--require-gates` when QA report evidence is required.

For pages containing formal text, also build `text-layout-manifest.json` with
`scripts/text_model.py build`. `TextSpec.content` is the formal string and
`TextSpec.runs[]` preserves mixed styling and line breaks; validate it before
composition with `scripts/text_model.py validate`. Keep logos as
`brand_lockup` assets, not TextSpecs, and do not change historical R13 files
just to add the new sidecar manifest.

## State machine

Persist `state`, `batch_id`, artifact paths, approvals, blockers and next action in the handoff file. A small task may merge adjacent states only when the merge reason and unchanged gates are recorded.

| State | Enter condition / required input | Actions and output | Validation | Allowed next | Failure state |
|---|---|---|---|---|---|
| `intake` | request received; available inputs | deck brief + source paths | goal and required-input status recorded | `source-analyzed`, `revision-required` | `revision-required` |
| `source-analyzed` | readable inventory | extract themes/facts/conflicts → source inventory | every claim has source/status | `outline-draft` | `revision-required` |
| `outline-draft` | brief + source inventory | draft table using outline contract | required fields and continuous slide numbers | `outline-review` | `revision-required` |
| `outline-review` | valid draft | collect owner notes and decisions | every page is approved/blocked/revised | `narrative-approved`, `revision-required` | `revision-required` |
| `narrative-approved` | user approves order/core messages | lock approved narrative version | approval identity/time/version recorded | `design-system-ready` | `outline-review` |
| `design-system-ready` | approved narrative + visual constraints + valid route decision | persist design tokens/components | required tokens and page families defined | `visual-draft` for `visual-creation`; `reconstruction` for `reference-reconstruction` | `revision-required` |
| `visual-draft` | `visual-creation` route + design system + approved pages + discovered image-generation capability | use an image-generation skill/tool/model to create high-quality per-page visual images + manifest | generated images represent purpose/focus/flow/layout and pass visual review | `visual-approved`, `revision-required` | `revision-required` |
| `visual-approved` | user accepts visual direction | lock visual refs and exceptions | approved refs mapped to pages | `reconstruction` | `visual-draft` |
| `reconstruction` | approved outline + approved visual/reference images + available source assets + reconstruction contract | decompose each reference and engineer an editable PPTX without redesign; create slide/object manifest | formal text authority, object treatment, substitutions, placeholders and provenance recorded | `rendered` | `revision-required` |
| `rendered` | PPTX saved | render pages and record manifest | expected pages render without tool error | `validated` | `revision-required` |
| `validated` | render + structural reports | run page/deck gates | no blocker and threshold met | `human-closeout` | `revision-required` |
| `revision-required` | blocker or rejected gate | issue log + bounded fix (max 3 automatic rounds) | fix re-rendered/rechecked or escalated | prior relevant state | `revision-required` |
| `human-closeout` | automated gates pass | user checks value, facts, aesthetics, unresolved placeholders | explicit sign-off or documented rejection | `delivered` | `revision-required` |
| `delivered` | sign-off + delivery check pass | PPTX + reports + handoff | deliverables exist and report is truthful | none | `revision-required` |

## Source and outline flow

Use `scripts/inspect_sources.py` for deterministic inventory when supported. Distinguish sourced fact, attributed opinion, model inference, and engineering assumption. Mark unverifiable content `待验证`. Ensure report parent directories exist before writing outputs; a report-write failure is a runtime blocker, not a successful empty report. For image references, always preserve the original pixel dimensions separately from any downsampled analysis dimensions; `scripts/probe_palette.py` reports both `source_size` and `sample_size`.

Build the outline before PPTX. Follow `references/outline-table-contract.md`. Every page needs purpose, one-sentence core message, relationship to adjacent pages, expression type, must-keep content, removable/mergeable content, source, audience takeaway, owner notes and status. Run `scripts/validate_outline.py`. Do not enter reconstruction before narrative approval.

## Design and visual intermediate

Follow `references/design-system.md` and persist ratio, grid, margins, font hierarchy, colors, chart palette, spacing, radius, shadows, lines, icon/image treatment, backgrounds and components. Prefer deck-wide consistency over isolated-page novelty.

Classify each page as `title`, `agenda`, `section`, `comparison`, `timeline`, `process`, `framework`, `matrix`, `funnel`, `pyramid`, `map`, `chart`, `table`, `infographic`, `scene`, `quote`, `summary`, or `appendix` using relationship, reading order, audience, conclusion importance, density and whether comparison/causality/process/hierarchy/space is being expressed. Do not default to four cards, icon rows, text over a background, or blind template substitution.

Visual intermediates confirm layout, proportions, hierarchy, space, color, reading path, focus and rhythm. They are not formal text. Follow `references/visual-intermediate.md`; review with `references/visual-review.md`. This is separate from reference reconstruction: a generated raster is required for `visual-creation`, while an approved fixed reference is sufficient visual authority for `reference-reconstruction`.

**Hard gate:** when the workflow includes `visual-draft`, invoke an available image-generation skill, tool, or multimodal image model—prefer the installed `imagegen` skill when available—to generate a genuinely high-quality raster visual draft. A manually arranged PPTX page, native-shape wireframe, template substitution, HTML/SVG mockup, or render of an already-built PPTX is not a completed visual intermediate and must not be labeled as one. Record generator, model/tool, prompt, image path and review status in `visual-intermediate-manifest.json`.

Target the requested presentation context, such as high-end state-owned-enterprise reporting, executive review, product launch, academic defense or roadshow; “high quality” is observable through coherent hierarchy, intentional composition, professional typography scale, disciplined color, adequate whitespace, clear focal point and deck-wide stylistic consistency. Generated text is provisional and may be inaccurate; never copy it into formal PPTX content. If image generation is unavailable, fails after the bounded retry, or is explicitly skipped by the user, record `visual_intermediate_status: unavailable|skipped`, state the reason and stop at the relevant gate unless the selected route is `reference-reconstruction` and the approved reference image itself is the visual authority.

## PPTX reconstruction

Follow `references/reconstruction-contract.md`, `references/editability-levels.md`, `references/native-object-protocol.md`, and—when applicable—`references/icon-asset-protocol.md`. Default to 16:9 unless explicitly overridden. Reuse an existing PowerPoint master/layout through `layout_name` or `layout_index` when a template is supplied; record the selected layout and treat unknown layout references as blocking errors. Use real text boxes for titles/body/labels/notes/numbers; native shapes for simple geometry and deterministic gradients; SVG as a moveable vector asset unless internal path editability is explicitly proven; groups for semantic components whose child shapes must remain independently editable; native tables and charts when source data is traceable; deck theme tokens for consistent defaults; and speaker notes in the notes part rather than on-slide text. For icons/decorations/artistic typography, inventory every object before implementation, keep them out of the frame layer unless intentionally part of it, use alpha-preserving extraction/splitting, and validate `icon-asset-manifest.json`. For every icon-bearing reference reconstruction, require per-page `imagegen-assets-manifest.json` with `generated_source`, `copied_to`, `layer`, `prompt_file`, `backend`, and `key_color`; run `scripts/validate_imagegen_assets_manifest.py` before composition. Missing or non-imagegen evidence blocks the page. Assign every visible object an `editability_level` from `L0` to `L5`, derive the page summary, and never use a whole-slide image as the only slide content. Document placeholders for unreconstructable visuals.

Treat reconstruction as **reference image → editable PowerPoint engineering**, not as a redesign brief. Before the first page, acknowledge the contract and confirm the reference image, formal-text authority and available source assets; if the user explicitly asks to discuss the protocol first, do not generate. For each page, analyze the reference, decompose it into editable text/native shapes/vectors/independent images/placeholders, implement that plan, render the page, compare hierarchy/structure/spatial relationships, and verify that required objects remain editable. Do not improve, simplify or rearrange an approved reference merely because another design seems preferable.

Brand marks and logos are not ordinary editable copy. Keep a logo's complete mark and wordmark as one independent movable image or vector asset from an authoritative source; do not recreate Chinese/English logo lettering as ordinary text unless the user explicitly requests a redesigned or editable logo. Document this as an asset exception to text editability, and verify that no duplicate logo text remains underneath.

Conflict priority: explicit user requirement > approved outline > approved design system/visual > domain hard constraint > original source > agent preference. Formal text comes from the approved outline; reference/visual images govern layout and visual relationships. Reconstruction priority is information hierarchy > page structure > spatial relationship > typography > graphics/icons > decoration. Record tradeoffs.

### Text-style reconstruction protocol

For reference-image reconstruction, plain text transcription is insufficient. Build a text-style map before composition: each visible text region must record `source_bbox`, font size, weight, color, line spacing, paragraph spacing, alignment, and wrap width. Any sentence containing emphasis must be split into `runs`; preserve color/weight for section labels, bullets, numbers, prices, percentages and redacted placeholders. Do not use literal Markdown markers such as `**元` as visible text unless the reference visibly contains the asterisks; represent redaction with the exact visual glyphs and style. The overview, title accent and footer are also rich-text candidates and must be audited separately. Render once with native text and once with the task-local font, then compare line breaks and emphasis against the reference. A page is not text-faithful when the words are present but emphasis, line breaks, or text-box boundaries materially differ.

For every reconstructed or repaired deck, also create `slide-object-manifest.json` using the contract in `references/object-manifest.md`. Use `scripts/build_object_manifest.py` for the deterministic baseline, then review Logo and other authoritative assets before composition. `layout.json` owns geometry; the object manifest owns semantic roles, provenance, editability level and expected final shape identity. Run `scripts/validate_object_manifest.py`; then run `scripts/inspect_editable_objects.py` against the final PPTX. A semantic panel, logo, product image or footer component must have its own object record when it is independently movable; a manifest claim is not evidence until the final PPTX shape-name audit confirms it.

When repeated panels are visually obvious but their coordinates are unknown, use `scripts/detect_panel_candidates.py` as a proposal step and read `references/panel-detection.md`. Do not assume a fixed count or grid; `--rows/--cols` are optional hints only. Its result is never authoritative: keep `status: needs-human-confirmation`, then use `scripts/approve_panel_candidates.py --approve --reviewer ... --revision ...` after visual review to create an approved manifest with corrected full-resolution bboxes and source hash. `extract_panels.py` must reject unapproved candidates. Exclude logos, intro/footer components and unbounded gradients before extraction. R13's 2×3/6-panel case belongs only in regression fixtures.

Use the backend selected by `probe_environment.py`, and record the actual
composer backend in the environment report. If a compatible `ppt-master`
installation is available, adapt through its documented paths; never claim it
exists when discovery fails and never copy it wholesale. A repeated card grid
is not one frame: split semantic panels into native shapes or one transparent
image per region, and keep formal text above them as native text. Independent
movement of a picture asset is not the same as internal vector editability;
declare both explicitly.

When the selected composer is `python-pptx` and the delivery requires bundled
fonts, compose to a new staging PPTX, then run
`scripts/embed_fonts.py staging.pptx final.pptx --font-dir project-fonts
--report font-embedding.json`. The adapter writes PresentationML font
relationships and `.fntdata` parts without mutating the staging source; run
`scripts/inspect_pptx.py` on the final file and render that final file. Do not
label a sidecar font as embedded. A font with restricted OS/2 embedding rights
must be rejected, and an unsupported font container such as TTC must be split
to a licensed face before embedding.

## Render, validation and repair

After each page/batch: save, render, inspect openability, overflow risk, overlap, bounds, fonts, numbers/units, missing/blank content and reference-layout relationship. For reference reconstruction, run `validate_text_style_map.py layout.json --require-source-bbox` before composition and treat missing runs for visibly emphasized text as a repair item. For repeated panels, inventory all components before deleting a whole frame, use `extract_panels.py` with full-resolution bboxes, create `panel-asset-manifest.json`, and run `validate_panel_assets.py --require-independent --assets-dir ...`; a whole-slide frame containing semantic cards is a blocker. For icon-bearing pages, run `probe_palette.py`, `chroma_key.py`, `slice_grid.py`, `validate_imagegen_assets_manifest.py`, `validate_icon_assets.py`, `audit_icon_layers.py`, and `placement_qa.py` as applicable; for every imagegen chroma-key layer, pass the B1-selected color explicitly with `--auto-key none --key-color` and verify the output reports nonzero transparency—automatic border sampling is not authoritative for generated neon/gradient backgrounds. Require B4 source-vs-frame evidence, B5 cutout/split evidence, contact-sheet inspection, and source/preview bbox replay before accepting icon placement. After the deck: check ratio, typography, palette, rhythm, chart data, assets, slide-level independent panels, OOXML structure, editability/flattening, notes/sources/links and openability.

Use `scripts/run_pipeline.py` as the default verification entrypoint for an existing or reconstructed deck. It runs environment/font probes, structural inspection, rendering, non-blank visual gates, optional reference-image comparison, optional OCR readback, route validation, manifest/editability validation, project-level consistency and a unified project-report aggregate in an isolated run directory. When `slide-object-manifest.json` exists, the runner automatically validates it and reverse-audits the final PPTX; use `--require-object-manifest --require-independent-panels --expected-panel-count N` to make those gates mandatory, `--require-panel-approval` to require an approved panel manifest even when no panel file is present, and `--require-text-style-map` to enforce the rich-text gate. Any discovered panel manifest is validated as human-approved. For a new or reconstructed project, pass `--route-decision route-decision.json --require-route --require-editability`; the runner records route authority and per-object L0-L5 evidence. Its `pipeline-result.json`, `project-validation.json` and `project-report.json` must expose the render gate, visual comparison, route, editability, report registry and OCR status as quality evidence; an optional OCR language that is unavailable is a recorded degradation, not a false pass. For a one-page reference use `--reference IMAGE`; for a multi-page deck use `--reference-dir DIR` containing matching `slide-1.png`, `slide-2.png` and so on. Never compare only the first page of a multi-page deck. Use `--revision-label Rn` before a repair batch to create an immutable snapshot; use `scripts/revision_guard.py materialize` to create a separate recovery work copy. Never let the runner update handoff state or claim human approval. The lower-level commands remain available for targeted diagnosis. Run `validate_render.py` after rendering with the expected page count and critical regions when known. Use `compare_visual.py` for a single approved reference or `compare_visual_deck.py` for every page in an approved reference directory; their metrics are diagnostic and font-sensitive. Use `ocr_text_check.py --require-ocr` only when the requested Tesseract language model is installed; otherwise record `unavailable` and retain human review. For a font-embedded output, include the post-processor report in the run evidence and let the final `inspect_pptx.py`/font-delivery gate, not the staging file, be authoritative. Validate closeout JSON with `validate_signoff.py` before delivery, then pass its report to `delivery_check.py --signoff-report --project-report project-report.json --require-project-report --route-validation route-validation.json --manifest-validation manifest-validation.json --require-route --require-editability` together with `--render-visual-gate`, `--visual-comparison` and `--ocr-report` when those gates were run. Pass `--handoff` and `--expected-ratio 1.7777778` to `delivery_check.py` for the default 16:9 route. Script failure is a blocker. Automated repair is limited to three rounds; each round must update the issue log and repeat rendering and validation. Then escalate honestly. See `references/object-manifest.md`, `references/panel-detection.md`, `references/report-protocol.md`, `references/failure-recovery.md`, `references/workflow-flowchart.md`, `references/editability-levels.md`, and `references/quality-rubric.md`.

Before `run_pipeline.py --release`, produce the final file with the embedding
adapter when font embedding is required; the pipeline must inspect and render
that final output, never the staging PPTX.

For strict release, run `run_pipeline.py --release` with a task-local
`--font-dir`, `--route-decision`, `--handoff`, `--human-signoff`,
`--target-review` and `--quality-score`. This profile implies CJK asset
validation, typed editability, the font three-signal gate, WPS desktop/iPhone
review evidence, route validation and OOXML embedded-font verification, then
writes `release-check.json`. `pipeline-result.json.valid` remains a technical
result; only `release_eligible: true` means the automated release gate passed.

Before committing or publishing a skill change, run
`python3 scripts/run_tests.py --report test-report.json`; this executes the
repository regression programs and parses every `evals/*.yaml` fixture without
assuming pytest is installed.

Read `references/font-embedding.md` when the selected composer needs the
repository's OOXML font post-processor; it documents the package parts,
licensing gates, commands and the distinction between structural verification
and target-device proof.

## Human confirmation points

Require user confirmation for goal/audience/core conclusion, narrative order, visual direction, priority pages, important facts and numbers, unresolved assets, and final value/aesthetic judgment. Never silently change approved narrative or visuals.

Visual comparison note: same-aspect-ratio render/reference images are normalized to a common pixel size before metrics are calculated; a true aspect-ratio mismatch remains a blocker. Metrics are diagnostic and font-sensitive, so they never replace human visual review.

Layout gate note: `run_pipeline.py` records layout warnings without blocking by default; pass `--strict-layout` when missing `source_bbox` or another warning must stop the run. Geometry errors always block. An asset's `source_bbox` describes the full placed asset region, including intentional padding; do not use a logo symbol's sub-crop as the bbox for a full wordmark asset.

Project manifest note: after `slide-object-manifest.json` is reviewed, use `scripts/build_slide_manifest.py` to derive the canonical project `slide-manifest.json`; it copies object-level editability evidence but never invents approval, formal content or human closeout.

## Cross-session recovery

At every batch boundary save current batch, completed/pending pages, approved outline version, design system, asset and slide manifests, report index and aggregate, known issues, completed checks, contract version and next action. On resume, run consistency checks, verify report and deck hashes, report recovered state, and process only unfinished work. Follow `references/context-handoff.md` and `references/report-protocol.md`.

## Final response

Report each capability as one of `已实现`, `已验证`, `已创建但未验证`, `只有接口`, `需要人工处理`, `当前环境不支持`; include evidence/command for `已验证`. Also report delivered artifacts; current state; completed checks; unresolved blockers/placeholders; automatic repair rounds; assumptions marked `待验证`; user decisions required; and next action. Do not say “completed/delivered” unless the PPTX exists, opens, renders, required manifests agree, blockers are closed, quality gates pass, and human closeout is recorded.
