---
name: ai-ppt-editable
description: Turn approved slide images, screenshots, rasterized PDF pages, image-slide intermediates, existing PPT/PPTX, or structured content into editable, rendered, technically validated PowerPoint. Trigger for “图片转可编辑PPTX/截图还原PPT/复刻版式/图标分层/文字提取/现有PPT修复”, reference reconstruction, native object authoring, or PPTX rendering and technical QA. It can run standalone or as the editable worker for $ai-ppt-plus. Do not use for whole-page image generation or deck-wide narrative/release; use $ai-ppt-visual-gen or $ai-ppt-plus.
metadata:
 package_revision: 2026.08.29.21
---

# AI PPT Editable

## Boundary and runtime

Create or repair editable PPTX while preserving the declared visual and text
authorities. This worker owns decomposition, object planning, authoring,
rendering, technical QA, and technical repair. It does not own narrative
redesign, deck-wide release, or human sign-off.

This skill is independently installable and invokable. Run commands from this
skill directory; its reconstruction scripts, references, templates, schemas,
font assets, route contract, and tests are all local. Validate this package and
its standalone routing contract before work:

```bash
python3 scripts/validate_skill_package.py --skill-dir .
python3 scripts/validate_routing_contract.py
```

The split changes ownership and invocation only. Do not alter the checked-in
image-to-PPTX decomposition, asset extraction, composition, rendering, or QA
algorithms merely to satisfy this skill boundary.

## Authority model

In orchestrated mode, consume the immutable route decision, approved outline,
formal-text authority, design revision, reference roster, editability target,
and worker manifests supplied by `$ai-ppt-plus`.

For `native-authoring`, consume `route-decision/v2` with
`visual_authority: approved_design_system` and a declared
`native_content_manifest`. This route never silently falls back to whole-page
image generation or reference reconstruction.

In standalone mode:

- the supplied reference is visual authority unless the user asks for redesign;
- user-provided copy is formal authority;
- OCR/vision transcription is proposed text with confidence/uncertainty, not an
  unquestioned fact source;
- missing brand assets, chart data, or illegible text are blockers or explicit
  placeholders, never invention.

Read `references/reconstruction-contract.md`,
`references/editability-levels.md`, `references/native-object-protocol.md`, and
the asset/text/chart protocols relevant to the page.

## E0 — Intake, isolation, and preflight

1. Preserve originals and create a unique run root. Record source hashes and
   page-to-reference mapping; never overwrite a baseline or input deck.
2. Normalize only derived comparison/render copies. The original remains
   authoritative and keeps its own hash.
3. Probe authoring/render/font/OCR capabilities and validate the selected
   backend binding. For CJK, validate the task-local font and rendering evidence.
4. Persist route and formal-text authority. A blocked or undecided route cannot
   enter composition.

## E1 — Inventory and object plan

For every page, inventory visible content independently: background, frame,
panels, text boxes/runs, charts, tables, icons, logos, decorations,
illustrations, artistic typography, and page furniture. Record source bbox,
layer, z-order, anchor, editability level, replaceability, and provenance.

Choose the highest practical editability level without mislabeling:

- native text, shapes, tables, and charts where semantics/data are known;
- movable raster/vector assets for icons, illustrations, and complex artwork;
- a whole-page bitmap only as an explicitly image-only fallback, never as an
  editable reconstruction.

Repeated semantic panels remain independently movable. Do not merge the entire
framework into one image unless the user explicitly accepts that level.

## E2 — Reference decomposition

For fixed-reference reconstruction, preserve page ratio, layout, hierarchy,
spatial relationships, palette, and visible styling. Separate:

1. background texture/photography;
2. frame/skeleton that excludes text and independent assets;
3. icons, decoration, logos, illustrations, and artistic words;
4. editable formal text;
5. charts/tables with their own data/representation authority.

Use `references/icon-asset-protocol.md` for B4/B5 provenance and cutout QA,
`references/panel-asset-protocol.md` for independent panels,
`references/text-style-protocol.md` for mixed color/weight/line breaks, and
`references/chart-reconstruction.md` for every chart. A source crop is valid
only with bbox and source hash; missing assets use the declared generation
route and remain independent assets after extraction.

Do not call `$ai-ppt-visual-gen` to replace an approved fixed reference. An
isolated missing icon/decoration generation event is allowed under the asset
provenance contract and does not change the page route.

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

## E4 — Render and validate

Render every page and run structural, object, asset-hash, font, text-layout,
overflow, overlap, panel, chart, route, and preview-consistency gates applicable
to the project. Compare against the authoritative reference when one exists.
Review both a deck strip and full-resolution pages.

Automated checks are technical evidence. Record `human_visual_review_required`
when applicable and never synthesize approval metadata.

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

## Blocking conditions

- missing formal-text or visual authority;
- whole-page bitmap presented as editable output;
- icon/panel/chart/text objects missing provenance or required independence;
- source/reference hashes drifted after planning;
- font, render, overflow, overlap, or package blockers remain;
- technical pass represented as human approval;
- reconstruction redesigns the approved reference without explicit user scope.
