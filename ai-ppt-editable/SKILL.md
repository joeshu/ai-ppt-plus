---
name: ai-ppt-editable
description: Turn approved slide images, screenshots, rasterized PDF pages, image-slide intermediates, existing PPT/PPTX, or structured content into editable, rendered, technically validated PowerPoint. Trigger for “图片转可编辑PPTX/截图还原PPT/复刻版式/图标分层/文字提取/现有PPT修复”, reference reconstruction, native object authoring, or PPTX rendering and technical QA. It can run standalone or as the editable worker for $ai-ppt-plus. Do not use for whole-page image generation or deck-wide narrative/release; use $ai-ppt-visual-gen or $ai-ppt-plus.
metadata:
  package_revision: 2026.09.19.02
---

# AI PPT Editable

## Boundary and runtime

Create or repair editable PPTX while preserving declared visual/text authorities. This worker owns decomposition, object planning, authoring, rendering, technical QA and responsible repair. It does not own narrative redesign or deck-wide human sign-off.

New strict image-to-editable work uses JavaScript ESM with `@oai/artifact-tool`. Validate the package and routing contract before work. Python is inspection/QA only, not an authoring fallback.

The detailed reconstruction loop and Knight-derived fidelity rules are defined in `references/astra-visual-reconstruction-engine.md` and `references/knight-fidelity-port.md`; final asset boundaries are defined in `references/imagegen-final-asset-policy.md`.

## Operating principle: reconstruct first, validate what matters

For fixed-reference work, use the Knight-style execution order:

`reference -> visual inventory -> native_editable/imagegen_asset classification -> assets -> fresh editable PPTX -> fresh render -> full-page + local-crop review -> object-level repair -> re-render`.

The first authored PPTX is a draft. PageGraph, TextGraph, ChartGraph and manifests support reconstruction and repair; they are not a replacement for looking at the fresh render. Do not add a new blocking contract merely because a visual metric is imperfect. Deterministic correctness defects are hard blockers; visual-fidelity metrics guide the repair loop only. There is no universal numeric visual threshold for normal execution or delivery.


## Mandatory execution contract

A normal image-to-editable run is self-contained and must not depend on running another skill or an A/B comparator. Track these phases for every page and do not claim completion if a required phase is skipped:

1. `input_prepared`: freeze source path/page, dimensions, aspect ratio and SHA-256.
2. `visual_inventory_done`: inventory all major text blocks, cards/panels, tables, charts, arrows/connectors, icons, logos, decorations and complex visuals with stable IDs and approximate source bboxes.
3. `asset_classification_done`: classify every non-text visual as exactly `native_editable` or `imagegen_asset` before authoring.
4. `imagegen_assets_done`: every `imagegen_asset` must have a generated source, final independent transparent PNG, provenance, native-alpha validation and crop/contact-sheet QA. If ImageGen is unavailable or repeatedly fails, stop and report the blocker; never silently substitute a script-drawn icon, source crop or low-quality approximation.
5. `text_fit_done`: determine the true usable text slot first, then text-fit every visible native text object; geometry/margins/wrap are repaired before font shrink. CJK runs must write Latin/East-Asian/complex-script typeface metadata required for stable PowerPoint rendering.
6. `pptx_built`: author native text/shapes/tables/connectors and independently movable image assets; preserve stable object IDs.
7. `z_order_done`: perform a physical layer-order pass. Preserve native internal order, place independent visual assets at the intended layer, then ensure readable text/labels are not hidden or clipped.
8. `render_qa_done`: fresh-render the exact PPTX and compare full page against the immutable reference.
9. `local_crop_qa_done`: inspect same-coordinate crops for dense cards, icon slots, charts, arrow-label components, bottom bars and user-flagged regions.
10. `repair_done`: map every material visual defect to the responsible object/layer, repair that object, and re-render. Do not repair by chasing a single scalar score.
11. `validation_done`: run editability, text, asset-alpha, semantic table/chart and provenance checks; only hard correctness defects block delivery.

The compact execution report should record these phase results and evidence paths. A/B comparison with Knight or any external baseline is an evaluation workflow only; it is never required for ordinary skill execution.

## Authority and decomposition

The supplied reference is visual authority unless the user requests redesign. User-provided copy is formal authority. OCR/vision transcription is proposed text with confidence, never invented fact.

Inventory each page before authoring: background/frame, text, cards/panels, charts, tables, arrows/connectors, icons, logos, decorations, illustrations and page furniture. Assign stable object IDs and approximate source bboxes.

Classify every non-text visual into exactly one practical reconstruction class:

- `native_editable`: text, cards, panels, dividers, ordinary arrows/connectors, simple badges, semantic tables and charts whose data/meaning are known.
- `imagegen_asset`: icons, pictograms, complex badges, decorative art, illustration fragments, complex ribbons/streams, artistic marks and other visuals whose faithful native reconstruction would require custom drawing logic.

Keep readable formal text native. Keep independent assets independently movable. A whole-page bitmap is never an editable reconstruction.

## ImageGen asset route

Generate every `imagegen_asset` as an independent transparent asset. Preserve genuine RGBA alpha; validate transparent corners, non-empty alpha bbox, padding and plausible subject coverage. Source crops are reference evidence by default, not final assets. If generation is unavailable or repeatedly fails, stop and request the explicit fallback decision rather than silently substituting a crop or script-drawn icon.

For grids, declare C×R, equal cells, safe zones and transparent padding; detect actual row/column centers before slicing. Repack by alpha-visible bbox and visual centroid. Contact sheets are QA evidence only and never enter the final asset directory.

## Text and geometry

Use native PowerPoint text for readable text. Preserve reference line topology and hierarchy. Measure dense text slots before authoring. Repair slot geometry, margins, icon/divider allocation and intended wrapping before shrinking font size. For Chinese text, set East Asian typeface metadata as well as the run family.

PageGraph/source bboxes are authoritative repair evidence for stable native panels, text slots and asset placement. Geometry calibration may project high-confidence source bboxes onto matching stable object IDs before text fit, but final correctness is determined by the fresh render and crop evidence.

## Charts and tables

Do not infer a table from borders, repeated rows or two-column alignment. Use semantic evidence: real fields/records/cells become native tables; icon+title+description repetitions remain repeated editable components.

Charts remain native/editable when the data are known. Missing future values stay blank and must never be serialized as zero. Validate the rendered plot and labels against the reference; a structurally valid chart can still be visually wrong.

## Authoring

Use the repository strict Artifact Tool adapter for new reference reconstruction. Preserve object IDs/names for selection-pane inspection and Repair Trace. Build in container -> icon/asset -> text order, then audit physical z-order. Do not reopen and resave a rich authored deck through `python-pptx` as a repair path.

## Render-driven QA and repair

After every meaningful authoring pass:

1. fresh-render the exact PPTX;
2. retain full-page reference/render, side-by-side, overlay and difference evidence;
3. crop and inspect dense cards, icon slots, chart areas, compact arrows, bottom bars and user-flagged regions at identical coordinates;
4. identify the responsible object/layer, not merely the lowest scalar score;
5. write an object-level Repair Trace containing accepted/rejected deltas;
6. repair only that layer and re-render.

Protect regional wins. A challenger that regresses whole-page fidelity is rejected unless an explicit human review determines the scalar regression is a renderer artifact and the visual/object evidence is better.

### Hard blockers

Fail closed for: provenance/hash mismatch; corrupt/unrenderable output; formal-text loss; whole-slide raster fallback; missing required independent assets; invalid alpha/clipping; semantic table/list error; chart blank-to-zero error; severe overflow/collision/out-of-canvas geometry; or required-editability loss.

### Visual metrics

Whole-page SSIM, balanced reference-fidelity score, regional SSIM and crop metrics are diagnostic during reconstruction. They rank repairs and detect regressions. Do not optimize a page by blindly chasing one scalar score.

There is no built-in 0.90 or other universal numeric visual pass threshold. Whole-page and regional metrics are diagnostic evidence for regression detection and repair prioritization. Final acceptance is based on render review, local-crop review, object/editability correctness, asset fidelity/provenance, semantic correctness and absence of hard blockers. A project may opt into an explicit numeric threshold only when the user or project contract supplies one.

## Final acceptance

A corrected final PPTX requires all of the following evidence:

- fresh PPTX and fresh render from the current source/candidate hashes;
- full-page and local-crop visual review;
- exact formal-text ledger match;
- object/editability inspection;
- independent asset/alpha QA and provenance;
- chart/table semantic checks where applicable;
- no hard blockers;
- Repair Trace showing the last accepted changes.

External A/B evaluation is optional and separate from normal execution. When explicitly requested, compare the corrected final candidate against the selected baseline on pixel/layout, text, object/editability, icon/asset and local-crop dimensions; never make ordinary delivery depend on another skill being available.
