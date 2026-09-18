---
name: ai-ppt-editable
description: Turn approved slide images, screenshots, rasterized PDF pages, image-slide intermediates, existing PPT/PPTX, or structured content into editable, rendered, technically validated PowerPoint. Trigger for “图片转可编辑PPTX/截图还原PPT/复刻版式/图标分层/文字提取/现有PPT修复”, reference reconstruction, native object authoring, or PPTX rendering and technical QA. It can run standalone or as the editable worker for $ai-ppt-plus. Do not use for whole-page image generation or deck-wide narrative/release; use $ai-ppt-visual-gen or $ai-ppt-plus.
metadata:
  package_revision: 2026.09.18.02
---

# AI PPT Editable

## Boundary and runtime

Create or repair editable PPTX while preserving the declared visual and text authorities. This worker owns decomposition, object planning, authoring, rendering, technical QA, and technical repair. It does not own narrative redesign, deck-wide release, or human sign-off.

The default Chinese presentation family is Microsoft YaHei (`微软雅黑`) as declared in `assets/default-font-policy.json`. Resolve it from the licensed Windows system font directory and record the exact file hashes. Never copy or redistribute Microsoft font binaries with this skill. If the family is absent, block or obtain explicit approval before using the bundled Noto fallback.

This skill is independently installable and invokable. Run commands from this skill directory; its reconstruction scripts, references, templates, schemas, font assets, pinned `requirements-ci.txt`, route contract, and tests are all local. The route contract contains a historical compatibility binding and a separate `strict_authoring` binding. New strict image-to-editable work may use only the latter: JavaScript ESM with `@oai/artifact-tool`. Validate this package and its standalone routing contract before work:

```bash
python3 scripts/validate_skill_package.py --skill-dir .
python3 scripts/validate_routing_contract.py
```

The worker remains independently runnable; when called by `ai-ppt-plus`, it consumes the orchestrator's approved handoff and returns worker-level technical evidence. It never owns deck-wide narrative, release eligibility, or human sign-off.

Keep image-to-PPTX decomposition, asset extraction, composition, rendering, and QA changes incremental, documented, and covered by focused regression tests. The current skill contract and quality gates are authoritative.

## Authority model

In orchestrated mode, consume the immutable route decision, approved outline, formal-text authority, design revision, reference roster, editability target, and worker manifests supplied by `$ai-ppt-plus`. Follow the current route contract for `visual-creation`, `reference-reconstruction`, and strict native authoring.

In standalone mode:

- the supplied reference is visual authority unless the user asks for redesign;
- user-provided copy is formal authority;
- OCR/vision transcription is proposed text with confidence/uncertainty, not an unquestioned fact source;
- missing brand assets, chart data, or illegible text are blockers or explicit placeholders, never invention.

Read `references/source-intake.md`, `references/source-crop-integrity.md`, `references/reconstruction-contract.md`, `references/editability-levels.md`, `references/native-object-protocol.md`, and the asset/text/chart protocols relevant to the page. For any table-like region, also read `references/semantic-layout-classification.md`. Use its three-state decision: native table, repeated component, or blocking ambiguous. Never default insufficient semantic evidence to a native table, and preserve reference geometry, styling, layering and independent editability. Do not infer a native table from borders, aligned rows or two columns alone. Icon/title/body lists are `repeated_component_group` regions and must not emit `a:tbl`; classify them before E3 and keep their children independently editable. For last-mile viewer compatibility and preservation, also read `references/ooxml-compatibility.md`. For the mandatory final visual-asset route, also read `references/imagegen-final-asset-policy.md`. For the strict image-to-editable hardening contracts, also read `references/optimization-validation.md` and `references/knight-fidelity-port.md`; do not replace the synchronized core with a simplified reconstruction path.

For every reference-led page, build and validate the current fidelity and authoring manifests. Generic symbols, missing source bboxes, unresolved object IDs, stale source/candidate hashes, silent flat-fill fallbacks, and undeclared stretching block the page. A technical pass remains `accept-for-human-review` until visual fidelity, formal text and editability are confirmed by a person.

## E0 — Intake, isolation, and preflight

1. Preserve originals and create a unique run root. Record source hashes and page-to-reference mapping; never overwrite a baseline or input deck.
2. Normalize only derived comparison/render copies. The original remains authoritative and keeps its own hash.
3. Probe authoring/render/font/OCR capabilities and validate the selected backend binding. For CJK, validate the task-local font and rendering evidence. When embedding fonts, the declared run family and the font's internal family must match exactly or through an explicit, audited alias map; unknown family mismatches are blockers. Record the resolved family and alias in the font report.
4. Persist route and formal-text authority. A blocked or undecided route cannot enter composition.

## E1 — Inventory and object plan

For every page, inventory visible content independently: background, frame, panels, text boxes/runs, charts, tables, icons, logos, decorations, illustrations, artistic typography, and page furniture. Record source bbox, layer, z-order, anchor, editability level, replaceability, and provenance.

Choose the highest practical editability level without mislabeling:

- native text, shapes, groups, tables, and charts where semantics/data are known;
- native shapes/groups for simple cards, panels, dividers, process nodes and table grids; each semantic container has its own object ID;
- movable raster/vector assets for icons, illustrations, logos/brand artwork, and complex artwork;
- a whole-page bitmap only as an explicitly image-only fallback, never as an editable reconstruction.

Repeated semantic panels remain independently movable. Simple semantic panels, cards, frames and tables are native by default. A text-free complex visual substrate may remain an independent image only when its manifest records the exception; it never replaces native text or a table object.

## E2 — Reference decomposition

For fixed-reference reconstruction, preserve page ratio, layout, hierarchy, spatial relationships, palette, and visible styling. Separate:

1. background texture/photography;
2. native frame/skeleton shapes/groups for simple geometry, or a text-free traceable complex visual substrate when native recreation would reduce fidelity;
3. icons, decoration, logos, brand lockups, illustrations, and artistic words;
4. editable formal text;
5. native charts/tables with their own data/representation authority.

Use `references/icon-asset-protocol.md` and `references/imagegen-sheet-slicing.md` for B4/B5 provenance, sheet slicing and cutout QA, `references/panel-asset-protocol.md` for independent panels, `references/text-style-protocol.md` for mixed color/weight/line breaks, and `references/chart-reconstruction.md` for every chart.

### Mandatory ImageGen asset route

Follow the Knight-style deterministic split: `native_editable` versus `imagegen_asset`. Do not add a separate automatic brand-exception classification stage.

Formal text/data and simple native PowerPoint primitives stay native. Every other non-native visual asset is `imagegen_asset`, including icons, pictograms, logos, logo lockups, brand marks, wordmarks, calligraphic slogans, signatures/seals, decorative city/skyline art, footer/header brand bands, ribbons, 5G marks, gradients, glows, textures, complex arrows, illustrations, badges and artistic typography. Native ImageGen is the required final-asset route even when an exact source crop can be isolated.

The source crop is reference evidence only: use it for bbox, prompt guidance, palette/style lock and source-vs-render/local-crop QA. Do not insert it as the final PPT asset by default. Do not use PIL/SVG/HTML/Canvas/matplotlib/PowerPoint-shape drawing as a substitute final asset for an `imagegen_asset`.

For B4 overlay assets, use transparent-first generation. Ask native ImageGen for genuine RGBA transparency on the first attempt and validate alpha. A valid transparent result goes directly to B5 slicing. If direct alpha fails, edit that same generated asset to transparency once. Only if the transparent edit also fails may the run request one flat chroma-key version and execute `chroma_key.py`. Record fallback level and key color; never cycle through multiple key colors.

For multi-asset generation, follow Knight's C×R/N×N discipline: generate complete assets inside safe-zone cells, detect real row/column centers before slicing, sample each cell edge independently for adaptive chroma-key, retain 20–25% padding, then repack by visible-alpha bbox and alpha visual centroid. Contact sheets are QA-only and must never enter the PPTX or canonical final asset directory.

A brand lockup whose lettering is inseparable from the artwork is one `imagegen_asset`; do not OCR/re-typeset its internal artwork. This rule does not permit formal body text, ordinary labels, numeric data or chart data to be rasterized.

If generation fails, pause and ask the user to choose exactly one: continue/retry native ImageGen, or use original-image crop/cutout (`source_reuse`). Never make that choice implicitly. Record the explicit user decision, reason and timestamp in the asset manifest; an undecided asset is blocked.

Only when the user separately supplies an authoritative standalone asset and explicitly asks to insert that exact file may the run use it directly. This is a user-directed source operation, not an automatic brand exception. Without that explicit instruction, ImageGen remains mandatory.

Each generated final asset must remain independent and movable. Its manifest record must include `asset_id`, `asset_class`, `provenance_mode: imagegen`, `generated_source`, `copied_to`, `prompt_file`, `backend`, delivered-file hash, source bbox, target bbox, and PPT object ID. Run `validate_imagegen_final_assets.py --strict` before composition and after final render.

Run the reference-fidelity asset-boundary subgate after the contact sheet and after the final render. It must check neighboring text/separators/header bands, matte rectangles, clipping, transparent padding, visible-alpha bbox, alpha centroid, and an effect-layer inventory for complex artwork. Hash/visibility/object-count passes do not waive these checks.

Do not use deck-wide visual generation to redesign an approved fixed reference. Invoke native ImageGen as a scoped element-generation event for each `imagegen_asset`; source reuse is reference evidence only unless the user explicitly approves the fallback above.

For every reference-led page, run the authoring contract gate before composition and again after the final render. Before issuing the Artifact Tool marker, every `reference-reconstruction` request must also run `scripts/reference_preflight.py` against its unique run root. A passing authoring-contract report alone is insufficient: it verifies the backend and native-object mechanics but cannot prove that the reference's imagegen asset inventory was covered. If PageGraph identifies any `imagegen_asset`, `reference_preflight.py` must find a strict `imagegen-assets-manifest.json` with one approved independent generated asset for every required ID. Missing coverage is a blocker; native-shape approximations are not a substitute.

```bash
python3 scripts/validate_authoring_contract.py --strict --report authoring-contract.json
```

The authoring contract is not a status note: it must identify the JS ESM builder, `@oai/artifact-tool`, exactly one artifact-operation marker, the actual final output, and each independent image exception. Missing or stale evidence blocks delivery; it is never repaired by rasterizing semantic content.

Use the repository-owned adapter for the strict authoring pass. It consumes the same normalized layout contract as the compatibility composer and writes the PPTX directly through Artifact Tool:

```bash
python3 scripts/compose_pptx.py layout.json output.pptx --authoring-backend artifact-tool --node "$CODEX_PRIMARY_RUNTIME_NODE" --node-modules "$CODEX_PRIMARY_RUNTIME_NODE_MODULES" --font-dir assets/fonts --strict-input
```

The command emits an adjacent `output.artifact-tool.json` report and inspect NDJSON. Keep the historical default only for frozen compatibility fixtures; new image-to-editable runs must select `artifact-tool` and retain its report.

Never assume a generated asset sheet is a uniform grid. Before B5, inspect alpha row/column spans and classify the sheet as `uniform_grid`, `variable_row`, or `artistic_row`. Fixed origin-based slicing is permitted only after uniform-grid evidence is recorded. For a declared grid, use `slice_grid.py --detect-grid` and require the expected row/column center counts; variable-row sheets require row-aware explicit crops, and complex artistic typography requires one full-row asset per visual line. Contact-sheet review must reject clipped glyphs, edge-touching circles, merged neighboring objects, or an art row split into character fragments. See `references/imagegen-sheet-slicing.md`.

For image-led improvements, run the bounded protocol in `references/optimization-validation.md`: preserve the immutable baseline, create an isolated candidate, run native-object, font, text, layout and visual gates, and roll back the candidate on any real replay regression.

For any post-composition compatibility repair, use only the ZIP-level `scripts/normalize_ooxml_relationships.py` adapter. Never reopen and resave the authored deck through `python-pptx` after rich text, independent assets, or gradients have been composed. Run `scripts/validate_repackaging_invariants.py` and block delivery if the slide part set, media bytes, picture count, text-run/style digest, or gradient count changes. This is a technical preservation gate; the repaired file still needs rendered visual comparison and human review.

## E3 — Author editable objects

Author the normalized layout through the strict backend. Keep semantic text, simple shapes, tables and verified charts native; place every approved `imagegen_asset` as an independent movable picture object with its declared bbox and z-order. Preserve object IDs/names for selection-pane inspection and repair traceability.

## E4 — Render and acceptance

Render the authored PPTX, then run full-page and hard-region comparison. Use the selected profile-aware visual gate; whole-page SSIM remains diagnostic outside the standard profile. Validate text, objects, generated assets, alpha geometry, local crops and source/candidate hashes. A visual pass never waives missing ImageGen provenance or editability blockers.

## E5 — Responsible repair

Repair only the responsible layer. For generated visual failures, regenerate/re-edit the failing asset or repair its alpha bbox/centroid/placement; do not replace it with a source crop unless the user explicitly approves that fallback. For text/layout failures, repair native text or geometry without rasterizing semantic content. Re-render and rerun the affected gates after every repair.
