# Visual repair patterns for fixed-reference reconstruction

This reference turns recurring fresh-render defects into reusable reconstruction rules. It is not a new visual gate. Each pattern creates a responsible-object repair action and a fresh re-render.

## 1. Typography density / line-topology drift

### Symptom

The formal text is present, but the candidate looks looser or denser than the reference: different line count, different line breaks, too much white space, or a title/subtitle wraps when the reference does not.

### Root causes

- The authoring slot is inferred from glyph pixels instead of the intended editable text slot.
- A repeated component reuses one global text width even though its icon/divider reservation differs.
- Text fitting uses only `max_lines`; it does not preserve the reference's exact line topology.
- The fit font and the PowerPoint authoring font are not the same resolved face.
- Inner margins, paragraph spacing or line spacing are changed to compensate for a wrong bbox.

### Required repair order

1. Recover/reference the intended text-slot bbox and exact reference line count.
2. Repair left/right/top/bottom inner margins.
3. Repair reserved icon/divider/bullet space.
4. Preserve the reference line count and intended wrapping.
5. Verify the same runtime-resolved font face is used for measurement and authoring, including CJK OOXML binding.
6. Repair paragraph/line spacing and runs.
7. Change font size only after geometry is correct.

Do not accept a fit merely because it does not overflow. A one-line reference becoming two lines is a visual defect even when both lines fit.

## 2. Pictogram identity drift

### Symptom

The candidate has an icon in the right location and color, but its contour/meaning is visibly different from the reference. Generic bars, books, users, warning triangles or document glyphs replace the original artwork.

### Root causes

- The visual inventory classified a semantic pictogram as a simple native shape.
- Authoring substituted a generic PowerPoint/native glyph because it was easy to edit.
- Asset QA checked alpha/placement but did not check artwork identity.

### Required classification rule

A reference pictogram/icon is `imagegen_asset` by default unless its visible artwork can be faithfully expressed by at most two ordinary native primitives without losing its identity. Logos, branded pictograms, illustrated badges and multi-part icons are independent assets.

Never replace a reference pictogram with a generic native icon solely to maximize editability. Editability is semantic: the icon remains independently movable as an asset while its nearby formal text remains native.

### Repair order

1. Compare artwork contour/identity in the final rendered crop.
2. If artwork identity is wrong, regenerate/rebuild the asset.
3. If artwork is right, repair alpha-visible bbox, visual centroid, scale, padding, clipping and z-order.
4. Re-render the icon in context; contact-sheet correctness is not final-slide correctness.

## 3. Anchored visual-system drift

### Symptom

A footer/header/background system is approximately present, but its wave height, skyline baseline, ribbon edge or brand mark is wrong. Foreground elements such as `5Gⁿ`, footer slogans or logos then appear vertically displaced even when their page coordinates seem reasonable.

### Root causes

- A complex visual system was fragmented into many native shapes instead of one semantic asset or a small semantic group.
- Child elements were positioned against the page rather than the parent visual region.
- Repair moved the child (`5Gⁿ`) before fixing the parent footer wave/skyline geometry.
- Local crop selection focused on individual objects and omitted the composed footer/header band.

### Required model

Represent composed systems with a semantic region, for example:

```json
{
  "object_id": "footer-system",
  "semantic_role": "footer-band",
  "bbox": [0.0, 0.82, 1.0, 0.18],
  "children": ["footer-wave", "skyline", "footer-left-copy", "5g-mark", "footer-right-copy"]
}
```

Complex wave/skyline art may be one `imagegen_asset`; readable slogans and brand text remain native above it. Child positions should be recorded relative to the semantic-region bbox where practical.

### Repair order

1. Repair parent region top edge/height/baseline and z-order.
2. Repair complex background asset scale/crop.
3. Re-anchor foreground children to the corrected parent region.
4. Re-render the whole semantic-region crop and then the full page.

## 4. Crop-selection blind spot

Object-only crop selection misses failures that emerge from relationships between objects. Every fixed-reference page should therefore include semantic-region crops in addition to object crops. When content occupies the bottom/top bands, include composed footer/header crops even if no single object spans the band.

The 5-10 crop budget should be diverse: dense text, at least one icon/pictogram cluster, major card/panel geometry, and composed header/footer/brand systems when present. Avoid spending the crop budget on near-duplicate neighboring objects.

## 5. Repair prioritization without a fixed visual threshold

Do not use `score < 0.90` or another universal threshold to decide whether a repair item exists. Rank regions by relative mismatch, material area, semantic importance and explicit issues, then inspect the 3-5 highest-impact regions per iteration. A high scalar score can still hide an obvious icon-identity or anchor defect.

The production state remains `repair-required` while material mismatches are still visible. Numeric metrics are evidence for ranking and regression analysis, not the acceptance authority.
