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
   - Required pattern: treat brand logos as independent source-bound assets unless an approved vector logo is provided. Preserve as a separate movable asset with source crop/hash/provenance, not as invented text or icon geometry.

3. **Icon semantics vs visual fidelity**
   - Bad pattern: rebuild all icons from generic Unicode symbols and accept the slide because card text is editable.
   - Failure: section icons lose style consistency and original line-art semantics.
   - Required pattern: classify repeated card icons as asset objects. Prefer approved icon assets or native image-generation followed by Asset QA v2. If the output must be fully editable, record this as an explicit icon-editability tradeoff and do not call the result pixel-perfect.

4. **Dense corporate card layout**
   - Bad pattern: infer card geometry from approximate equal thirds and then fit text by shrinking aggressively.
   - Failure: card title baselines, goal-strip padding, separator lines and body line breaks drift from the source.
   - Required pattern: lock a card-grid template first: header baseline, goal strip, icon column, body column, separator y-positions and section rhythm. Only after this template is fixed should text boxes be filled.

5. **Top strategy banner line wrapping**
   - Bad pattern: create one broad paragraph box and rely on renderer auto-wrap.
   - Failure: highlighted words move to wrong lines across renderers.
   - Required pattern: define the top paragraph as fixed rich-text runs with explicit line breaks matching the reference render. Highlighted terms remain in-line runs.

## Skill-rule backfill

For similar `corporate-card-grid` slides, `ai-ppt-editable` should apply the following reconstruction policy:

```text
corporate-card-grid policy
  1. Detect header, logo, top strategy banner and card grid as separate regions.
  2. Brand logo: source-bound independent asset unless an approved vector brand asset exists.
  3. Card grid: lock geometry before text fitting.
  4. Goal lines: one native rich-text TextSpec; no overlay emphasis text.
  5. Repeated section icons: independent assets or explicitly declared editable-icon approximation.
  6. Separators and card shells: native shapes.
  7. Render once and compare line wrapping, numeric emphasis and logo/icon fidelity before delivery.
```

## QA checklist

Before accepting a generated PPTX for this case type:

- [ ] All card body text is native editable text.
- [ ] Emphasized numbers are part of the same text object as the surrounding sentence.
- [ ] Logo is source-bound or approved vector; not approximated from a generic symbol.
- [ ] Card headers, goal strips and section separators align across all columns.
- [ ] Icons are either source/generation assets with provenance or explicitly recorded as editable approximations.
- [ ] Rendered preview is inspected for WPS/LibreOffice font-metric drift.
- [ ] Any asset approximation is listed in the user-facing comparison report.
