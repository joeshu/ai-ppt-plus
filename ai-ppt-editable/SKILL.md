---
name: ai-ppt-editable
description: Turn approved slide images, screenshots, rasterized PDF pages, image-slide intermediates, existing PPT/PPTX, or structured content into editable, rendered PowerPoint. Trigger for 图片转可编辑PPTX、截图还原PPT、复刻版式、图标分层、文字提取、现有PPT修复. It can run standalone or as the editable worker for $ai-ppt-plus.
metadata:
  package_revision: 2026.09.19.04
---

# AI PPT Editable

## Mission

Reconstruct or repair editable PPTX with the supplied reference as visual authority and user-provided copy as formal-text authority. For fixed-reference work, visual fidelity is determined from the fresh final render, not from process paperwork or a scalar score.

New strict reconstruction uses JavaScript ESM with `@oai/artifact-tool`. Python is inspection/QA only and is not an authoring fallback. Whole-page raster fallback is forbidden.

Read `references/knight-short-loop.md` for the normative production contract. `references/knight-fidelity-port.md` remains implementation guidance. External Knight A/B is a development/evaluation workflow, not a runtime dependency.

## Formal production chain

For normal fixed-reference reconstruction run this chain and no additional visual release-gate chain:

`Reference -> Visual Inventory -> native_editable/imagegen_asset -> Text Slot Preflight -> Asset Generation -> Artifact Tool Build -> Fresh PowerPoint Render -> Full-page Compare -> 5-10 key Local Crops -> Responsible Object Repair -> Re-render -> Hard Correctness Check -> Final PPTX`

PageGraph, TextGraph, ChartGraph, manifests, SSIM, pixel diff, five-dimensional A/B and other metrics may support diagnosis, traceability and regression analysis. They do not replace looking at the fresh render and do not independently block a visually repairable page.

## 1. Reference

Freeze source path/page, dimensions, aspect ratio and SHA-256. Historical PPTX, renders, PageGraphs or crops cannot satisfy a new run. The current source is immutable visual authority unless the user explicitly requests redesign.

## 2. Visual Inventory

Before authoring, inventory every visible element and classify it as `native_editable` or `imagegen_asset`.

Use `native_editable` for text, simple geometry, lines, connectors, simple tables/charts, card surfaces, labels and other elements that can be faithfully reconstructed with native PowerPoint objects.

Use `imagegen_asset` for logos, pictograms, icons, illustrations, decorative art, irregular gradients/textures and other complex visual assets whose identity or contour would be degraded by generic PowerPoint primitives. A reference pictogram/icon defaults to `imagegen_asset`; use native primitives only when the reference can be faithfully represented by no more than two ordinary primitives. Do not substitute a generic icon merely to increase editability.

For composite badges, model the plate/background, pictogram and label separately. Preserve the plate center/diameter, pictogram alpha-visible bbox, visual centroid and inset ratio; keep the label as native editable text.

## 3. Text Slot Preflight

Determine the actual text slot before shrinking fonts. Preserve the reference line topology, first baseline, baseline delta/line-height, paragraph spacing, inner margins and rich-text runs. `target_lines` is an exact topology constraint, not merely a maximum-line hint.

For title systems, treat title, subtitle/tag and divider/decoration as a parent title block. Calibrate parent geometry first, then child slots, visible glyph bbox/baseline, sibling spacing, font/weight and divider anchors. Do not independently nudge title children until the parent relationship is correct.

Runtime font resolution used for measurement must match the font family ultimately authored into PowerPoint/OOXML. CJK family binding must be explicit at OOXML level; fonts are environment capabilities, not repository binary dependencies.

## 4. Asset Generation

Generate required complex assets before deck authoring. Prefer native ImageGen. If transparent generation is unavailable, use chroma-key extraction from a deliberate green/red background. Do not fake transparency with white backgrounds and do not silently replace failed assets with generic scripted icons.

A failed required asset is a blocker. Stop and report it rather than degrading the reconstruction.

## 5. Artifact Tool Build

Author the PPTX through the official Artifact Tool route. Text remains native editable rich text; cards, simple geometry, lines and labels remain native shapes; complex visual assets remain independently movable images with true alpha where appropriate.

Do not use a whole-slide screenshot, a historical PPTX, a flattened full-page raster or a simplified Python authoring fallback.

For repeated columns/cards, calibrate relationships before individual objects: column widths, gaps, header/body spacing and icon/text insets should be corrected at the parent/group level before child nudging.

## 6. Fresh PowerPoint Render

Render the newly built PPTX through the configured PowerPoint-compatible renderer. The render used for comparison must correspond to the current PPTX bytes, not a previous candidate.

## 7. Full-page Compare

Compare the fresh render against the frozen reference. Global SSIM/pixel scores are diagnostic evidence only. A visually repairable mismatch does not become a production blocker because a scalar score is below a threshold.

## 8. Local Crops

Inspect 5-10 material same-coordinate crops per page. Prefer semantically distinct regions and include composite systems such as header/title bands and footer bands when present. If fewer than five material regions exist, inspect all of them.

Use local crops to identify the responsible object/system, not to produce another global pass/fail number.

## 9. Responsible Object Repair

Repair the object or parent visual system responsible for each mismatch, then re-render. Prioritize high-impact differences by semantic importance, affected area and relative visual discrepancy; do not use a fixed visual-score cutoff to decide whether an object deserves repair.

Common responsibility classes include:

- `title-block-geometry`: parent title geometry, child text slots, baselines, sibling spacing and divider anchors.
- `typography-density`: exact line topology, baseline rhythm, paragraph spacing, margins and rich-text runs.
- `composite-badge-identity`: badge plate geometry, pictogram alpha bbox/centroid/inset and editable label relationship.
- `anchored-visual-system`: parent contour/bbox, skyline or decorative baseline, child anchors and z-order.

For footer systems, calibrate in this order: parent bbox -> normalized wave contour landmarks/curve -> skyline baseline -> asset crop -> anchored children such as `5Gⁿ` and slogans -> z-order. Children must follow the parent system rather than page-absolute guesses.

Accepted repairs require a fresh after-render. Do not claim a repair from source-code changes alone.

## 10. Hard Correctness Check

Machine-blocking defects are limited to deterministic correctness failures:

1. corrupt/unopenable PPTX;
2. missing required text;
3. whole-page screenshot/flattened-page substitution;
4. objects required to be editable but delivered non-editably;
5. missing required assets;
6. fake transparency or clipped/cropped required assets;
7. severe text overflow/collision/container violation;
8. table/list semantic misclassification that changes the intended editable structure;
9. chart missing/null values silently converted to zero or other source-data corruption.

Visual similarity metrics, IoU, centroid drift, icon similarity, typography deltas, preview scores and other non-deterministic visual measurements are diagnostic/repair signals. They must not be promoted into additional ordinary production hard blockers.

## 11. Final PPTX

A final PPTX is ready only after hard correctness passes and the active Responsible Object Repair loop has no unresolved material repair items. Final state is expressed as `final-pptx-ready`; unresolved visual work is `repair-required`; deterministic correctness failure is `hard-correctness-fail`.

Do not claim completion solely because a metric threshold passed.
