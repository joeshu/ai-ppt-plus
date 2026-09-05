# Reconstruction lesson: China Unicom next-work card slide

Date: 2026-09-05
Source type: 16:9 raster slide with corporate logo, strategy banner, three vertical action cards, repeated icon/title/body sections, emphasized numeric goals.

## Observed reconstruction issues

This case exposed several recurring failure modes that are easy to miss when the slide is visually simple but dense:

1. **Numeric emphasis drift**
   - Bad pattern: create base goal text and then place a second red number text box on top.
   - Failure: the number overlaps surrounding copy after LibreOffice/WPS font substitution or text metric drift.
   - Required pattern: represent the full goal line as a single native text object with rich-text runs. The red/bold number must be a run in the same TextSpec, not an overlay object.

2. **Brand logo fidelity**
   - Bad pattern: approximate the China Unicom logo using generic symbols or reconstructed text.
   - Failure: logo identity and symbol geometry drift immediately, even if the rest of the slide looks acceptable.
   - Required pattern: treat brand logos as independent source-bound assets unless an approved vector logo is provided. Preserve as a separate movable asset with source crop/hash/provenance, not as invented text or icon geometry. Brand marks are the authorized-source exception to native imagegen.

3. **Icon semantics vs visual fidelity**
   - Bad pattern: rebuild icons from generic Unicode symbols, icon fonts, hand-drawn primitives, or source crops and accept the slide because card text is editable.
   - Failure: section icons lose line-art style, silhouette, semantic identity and cross-icon consistency.
   - Required pattern: classify every repeated card icon as an independent visual asset and send it through native imagegen. The source crop is reference/QA evidence only. The delivered final icon must carry `provenance_mode: imagegen`, prompt/backend/hash evidence and pass Asset QA v2. A source-reuse icon is allowed only after native imagegen fails and the user explicitly approves the fallback; it must never be selected silently.

4. **CJK font fallback / metric drift**
   - Bad pattern: author with a local CJK family name but do not bind a validated font asset or embed it in the delivered PPTX.
   - Failure: WPS/PowerPoint/LibreOffice substitutes a serif or differently measured font; titles shrink, line breaks move, body density changes and card geometry appears wrong even when the coordinates are correct.
   - Required pattern: reference reconstruction with CJK text must use the portable font route: font probe/resolution evidence, typography calibration, OOXML font embedding for release, and final rendered verification. Direct composition is blocked when a reference-reconstruction project contains CJK but `--embed-fonts`/font evidence is absent.

5. **Dense corporate card layout**
   - Bad pattern: infer card geometry from approximate equal thirds and then fit text by shrinking aggressively.
   - Failure: card title baselines, goal-strip padding, separator lines and body line breaks drift from the source.
   - Required pattern: lock a card-grid template first: header baseline, goal strip, icon column, body column, separator y-positions and section rhythm. Only after this template is fixed should text boxes be filled.

6. **Top strategy banner line wrapping**
   - Bad pattern: create one broad paragraph box and rely on renderer auto-wrap.
   - Failure: highlighted words move to wrong lines across renderers.
   - Required pattern: define the top paragraph as fixed rich-text runs with explicit line breaks matching the reference render. Highlighted terms remain in-line runs.

## Skill-rule backfill

For similar `corporate-card-grid` slides, `ai-ppt-editable` applies the following reconstruction policy:

```text
corporate-card-grid policy
  1. Detect header, logo, top strategy banner and card grid as separate regions.
  2. Brand logo: source-bound independent asset unless an approved vector brand asset exists.
  3. Every non-brand icon/illustration/complex visual: native imagegen final asset.
  4. Source crop for those visual classes: reference evidence only unless user explicitly approves fallback after imagegen failure.
  5. Card grid: lock geometry before text fitting.
  6. Goal lines: one native rich-text TextSpec; no overlay emphasis text.
  7. CJK reference reconstruction: portable font evidence + embedded font + typography calibration.
  8. Separators and card shells: native shapes.
  9. Render and compare line wrapping, numeric emphasis, icon fidelity, logo fidelity and font metrics before delivery.
```

## Runtime enforcement

The policy is not documentation-only:

- `validate_imagegen_assets_manifest.py` blocks icon/badge/gradient/illustration/complex-art final assets that use `source_reuse` without an explicit recorded user fallback decision.
- `reference_preflight.py` protects direct calls to `compose_pptx.py`: a `reference-reconstruction` project with icon/complex-visual objects must have a strict `imagegen-assets-manifest.json`; CJK content must use embedded-font evidence.
- The normal `run_pipeline.py` still performs the full typography calibration, font-delivery, semantic-object, visual-comparison and release gates.

## QA checklist

Before accepting a generated PPTX for this case type:

- [ ] All card body text is native editable text.
- [ ] Emphasized numbers are runs inside the same text object as the surrounding sentence.
- [ ] Logo is source-bound or approved vector; not approximated from a generic symbol.
- [ ] Every non-brand icon is a native-imagegen final asset with prompt/backend/hash provenance.
- [ ] No generic Unicode/icon-font substitute is present.
- [ ] No source-crop icon is delivered unless the user explicitly approved fallback after an imagegen failure.
- [ ] Card headers, goal strips and section separators align across all columns.
- [ ] CJK font resolution/embedding evidence is present and final render preserves the intended sans-serif metrics.
- [ ] Title single-line constraints and top-banner line breaks match the reference.
- [ ] Rendered preview is inspected for WPS/PowerPoint/LibreOffice font-metric drift.
