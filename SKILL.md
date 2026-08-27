---
name: ai-ppt-plus
description: Turn PDF, DOCX, Markdown, Excel/CSV, project files, meeting notes, images, existing PPT/PPTX, or approved outlines into narrative-coherent, visually consistent, editable, renderable, quality-checked PowerPoint deliverables. Trigger for “做PPT/幻灯片/演示稿/路演稿/汇报材料”, outline-first deck planning, image-model-generated high-end visual-intermediate design, slide reconstruction, PPTX redesign/inspection/repair, or resuming a multi-session deck. Outputs structured briefs, source inventories, outline tables, design systems, generated visual drafts, manifests, editable PPTX, validation and delivery reports. Do not trigger for a prose-only summary, a standalone image, spreadsheet-only analysis, or image-to-PPT reconstruction when the dedicated reconstruction skill is the narrower fit.
---

# AI PPT Plus

## Goal and boundaries

Build decks through explicit artifacts and gates: sources → structured outline → user approval → design system → visual intermediate → editable PPTX → render/validate → repair → human closeout. Never treat a generated slide image as the formal text source or as sufficient editable delivery.

Use for new decks, reference-led decks, outline-only or visual-only work, PPT/PPTX redesign, inspection, repair, charts, and multi-session projects. Exclude unrelated document writing, generic image generation, and tasks whose only goal is pixel-faithful image reconstruction; route the latter to `reconstruct-editable-pptx`.

## Start-up checks

1. Run `scripts/probe_environment.py --output environment-report.json` and `scripts/probe_fonts.py --output font-report.json [--font-dir project-fonts/]` before choosing a backend. A user-supplied, legally usable project font directory may be passed to `render_pptx.py --font-dir`; it is task-local and must still pass a rendered-page review. Chinese delivery remains blocked unless the font report and rendered-page review both pass. Otherwise select an explicit adapter, declared fallback, interface-only route, or blocked state. Never write commands/tools as though they exist without this evidence.
2. Read `references/source-intake.md`; inventory every source and record readability, authority, conflicts, missing facts, OCR needs, and sensitive-data signals.
3. Establish goal, audience, setting, language, page/time limit, deadline, output format, editability, formal data, brand/font rules, original assets, outline and references. Do not invent missing critical inputs.
4. Classify the task: text-only; text+references; reference-only reconstruction; existing deck redesign; PPTX inspection/repair; data chart; complex visual; incomplete input; outline-only; visual-only. Choose one mutually exclusive visual route: `visual-creation` when no approved fixed reference governs the page, or `reference-reconstruction` when a user/approved reference image governs the page. Before downstream work, persist `route-decision.json` from `assets/route-decision.template.json` (or the visual-creation template) and run `scripts/validate_route.py`; do not infer the route from a filename or from whether an image happens to exist.
5. Create or restore `deck-brief.md`, state, source inventory, outline, design system, asset/slide manifests, issue log, validation and delivery records. Create `report-index.json` for the project reports and produce `project-report.json` with the unified report envelope. Chat history is not authoritative state.
6. On resume or branch creation, run `scripts/validate_handoff.py handoff.json`. A missing artifact, missing required handoff field, PPTX hash mismatch, delivered state with blockers, or delivered state with remaining slides is a blocker; do not continue from chat memory.

## Routing

- Outline-only: stop after approved `outline.csv|xlsx` and narrative report.
- Visual-only: require approved outline or explicit visual brief; stop after reviewed visual manifest.
- Reference-only reconstruction: require formal text or mark text as transcription needing confirmation; preserve layout, do not redesign; use the approved reference as visual authority and do not invoke whole-page visual creation merely to satisfy a different route. The B4 asset-extraction route is a separate exception: when an isolated icon/decorative asset has no reliable original, an image-generation tool may generate only that frame-excluded asset sheet, with provenance and B5 cutout/split QA; it must not redesign the slide.
- Existing PPTX inspection/repair: inspect before mutation; preserve the original; render, diagnose, patch, and revalidate.
- Chart task: require traceable data and units; prefer editable chart or linked/reproducible data.
- Complex illustration: generate/extract only if provenance and fidelity are acceptable; otherwise place an explicit, documented placeholder.
- Incomplete critical input or unresolved conflict: move to `revision-required`, offer no more than three concrete choices, recommend one, and wait.

Read `references/narrative-strategy.md` for story decisions, `references/artifact-ownership.md` for authority/conflict rules, and `references/icon-asset-protocol.md` whenever a page contains icons, decorations, logos, illustrations or decorative typography.

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

Use `scripts/inspect_sources.py` for deterministic inventory when supported. Distinguish sourced fact, attributed opinion, model inference, and engineering assumption. Mark unverifiable content `待验证`. Ensure report parent directories exist before writing outputs; a report-write failure is a runtime blocker, not a successful empty report.

Build the outline before PPTX. Follow `references/outline-table-contract.md`. Every page needs purpose, one-sentence core message, relationship to adjacent pages, expression type, must-keep content, removable/mergeable content, source, audience takeaway, owner notes and status. Run `scripts/validate_outline.py`. Do not enter reconstruction before narrative approval.

## Design and visual intermediate

Follow `references/design-system.md` and persist ratio, grid, margins, font hierarchy, colors, chart palette, spacing, radius, shadows, lines, icon/image treatment, backgrounds and components. Prefer deck-wide consistency over isolated-page novelty.

Classify each page as `title`, `agenda`, `section`, `comparison`, `timeline`, `process`, `framework`, `matrix`, `funnel`, `pyramid`, `map`, `chart`, `table`, `infographic`, `scene`, `quote`, `summary`, or `appendix` using relationship, reading order, audience, conclusion importance, density and whether comparison/causality/process/hierarchy/space is being expressed. Do not default to four cards, icon rows, text over a background, or blind template substitution.

Visual intermediates confirm layout, proportions, hierarchy, space, color, reading path, focus and rhythm. They are not formal text. Follow `references/visual-intermediate.md`; review with `references/visual-review.md`. This is separate from reference reconstruction: a generated raster is required for `visual-creation`, while an approved fixed reference is sufficient visual authority for `reference-reconstruction`.

**Hard gate:** when the workflow includes `visual-draft`, invoke an available image-generation skill, tool, or multimodal image model—prefer the installed `imagegen` skill when available—to generate a genuinely high-quality raster visual draft. A manually arranged PPTX page, native-shape wireframe, template substitution, HTML/SVG mockup, or render of an already-built PPTX is not a completed visual intermediate and must not be labeled as one. Record generator, model/tool, prompt, image path and review status in `visual-intermediate-manifest.json`.

Target the requested presentation context, such as high-end state-owned-enterprise reporting, executive review, product launch, academic defense or roadshow; “high quality” is observable through coherent hierarchy, intentional composition, professional typography scale, disciplined color, adequate whitespace, clear focal point and deck-wide stylistic consistency. Generated text is provisional and may be inaccurate; never copy it into formal PPTX content. If image generation is unavailable, fails after the bounded retry, or is explicitly skipped by the user, record `visual_intermediate_status: unavailable|skipped`, state the reason and stop at the relevant gate unless the selected route is `reference-reconstruction` and the approved reference image itself is the visual authority.

## PPTX reconstruction

Follow `references/reconstruction-contract.md`, `references/editability-levels.md`, and—when applicable—`references/icon-asset-protocol.md`. Default to 16:9 unless explicitly overridden. Use real text boxes for titles/body/labels/notes/numbers; native shapes for simple geometry; editable or traceable charts; separate image objects for separate assets. For icons/decorations/artistic typography, inventory every object before implementation, keep them out of the frame layer unless intentionally part of it, use alpha-preserving extraction/splitting, and validate `icon-asset-manifest.json`. When an isolated missing asset is generated, require per-page `imagegen-assets-manifest.json` with `generated_source`, `copied_to`, `layer`, `prompt_file`, `backend`, and `key_color`; run `scripts/validate_imagegen_assets_manifest.py` before composition. Missing or non-imagegen evidence blocks the page. Assign every visible object an `editability_level` from `L0` to `L5`, derive the page summary, and never use a whole-slide image as the only slide content. Document placeholders for unreconstructable visuals.

Treat reconstruction as **reference image → editable PowerPoint engineering**, not as a redesign brief. Before the first page, acknowledge the contract and confirm the reference image, formal-text authority and available source assets; if the user explicitly asks to discuss the protocol first, do not generate. For each page, analyze the reference, decompose it into editable text/native shapes/vectors/independent images/placeholders, implement that plan, render the page, compare hierarchy/structure/spatial relationships, and verify that required objects remain editable. Do not improve, simplify or rearrange an approved reference merely because another design seems preferable.

Conflict priority: explicit user requirement > approved outline > approved design system/visual > domain hard constraint > original source > agent preference. Formal text comes from the approved outline; reference/visual images govern layout and visual relationships. Reconstruction priority is information hierarchy > page structure > spatial relationship > typography > graphics/icons > decoration. Record tradeoffs.

Use the installed presentation tooling or an explicitly configured compatible executor. If a compatible `ppt-master` installation is available, adapt through its documented paths; never claim it exists when discovery fails and never copy it wholesale.

## Render, validation and repair

After each page/batch: save, render, inspect openability, overflow risk, overlap, bounds, fonts, numbers/units, missing/blank content and reference-layout relationship. For icon-bearing pages, run `probe_palette.py`, `chroma_key.py`, `slice_grid.py`, `validate_imagegen_assets_manifest.py`, `validate_icon_assets.py`, `audit_icon_layers.py`, and `placement_qa.py` as applicable; require B4 source-vs-frame evidence, B5 cutout/split evidence, contact-sheet inspection, and source/preview bbox replay before accepting icon placement. After the deck: check ratio, typography, palette, rhythm, chart data, assets, OOXML structure, editability/flattening, notes/sources/links and openability.

Use `scripts/run_pipeline.py` as the default verification entrypoint for an existing or reconstructed deck. It runs environment/font probes, structural inspection, rendering, non-blank visual gates, optional reference-image comparison, optional OCR readback, route validation, manifest/editability validation, project-level consistency and a unified project-report aggregate in an isolated run directory. For a new or reconstructed project, pass `--route-decision route-decision.json --require-route --require-editability`; the runner records route authority and per-object L0-L5 evidence. Its `pipeline-result.json`, `project-validation.json` and `project-report.json` must expose the render gate, visual comparison, route, editability, report registry and OCR status as quality evidence; an optional OCR language that is unavailable is a recorded degradation, not a false pass. For a one-page reference use `--reference IMAGE`; for a multi-page deck use `--reference-dir DIR` containing matching `slide-1.png`, `slide-2.png` and so on. Never compare only the first page of a multi-page deck. Use `--revision-label Rn` before a repair batch to create an immutable snapshot; use `scripts/revision_guard.py materialize` to create a separate recovery work copy. Never let the runner update handoff state or claim human approval. The lower-level commands remain available for targeted diagnosis. Run `validate_render.py` after rendering with the expected page count and critical regions when known. Use `compare_visual.py` for a single approved reference or `compare_visual_deck.py` for every page in an approved reference directory; their metrics are diagnostic and font-sensitive. Use `ocr_text_check.py --require-ocr` only when the requested Tesseract language model is installed; otherwise record `unavailable` and retain human review. Validate closeout JSON with `validate_signoff.py` before delivery, then pass its report to `delivery_check.py --signoff-report --project-report project-report.json --require-project-report --route-validation route-validation.json --manifest-validation manifest-validation.json --require-route --require-editability` together with `--render-visual-gate`, `--visual-comparison` and `--ocr-report` when those gates were run. Pass `--handoff` and `--expected-ratio 1.7777778` to `delivery_check.py` for the default 16:9 route. Script failure is a blocker. Automated repair is limited to three rounds; each round must update the issue log and repeat rendering and validation. Then escalate honestly. See `references/report-protocol.md`, `references/failure-recovery.md`, `references/workflow-flowchart.md`, `references/editability-levels.md`, and `references/quality-rubric.md`.

## Human confirmation points

Require user confirmation for goal/audience/core conclusion, narrative order, visual direction, priority pages, important facts and numbers, unresolved assets, and final value/aesthetic judgment. Never silently change approved narrative or visuals.

## Cross-session recovery

At every batch boundary save current batch, completed/pending pages, approved outline version, design system, asset and slide manifests, report index and aggregate, known issues, completed checks, contract version and next action. On resume, run consistency checks, verify report and deck hashes, report recovered state, and process only unfinished work. Follow `references/context-handoff.md` and `references/report-protocol.md`.

## Final response

Report each capability as one of `已实现`, `已验证`, `已创建但未验证`, `只有接口`, `需要人工处理`, `当前环境不支持`; include evidence/command for `已验证`. Also report delivered artifacts; current state; completed checks; unresolved blockers/placeholders; automatic repair rounds; assumptions marked `待验证`; user decisions required; and next action. Do not say “completed/delivered” unless the PPTX exists, opens, renders, required manifests agree, blockers are closed, quality gates pass, and human closeout is recorded.
