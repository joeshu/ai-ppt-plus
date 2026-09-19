# Visual repair patterns for fixed-reference reconstruction

This reference turns recurring fresh-render defects into reusable reconstruction rules. It is not a new visual gate. Each pattern creates a responsible-object repair action and a fresh re-render.

## 1. Typography density / line-topology drift

### Symptom

The formal text is present, but the candidate looks looser or denser than the reference: different line count, different line breaks, too much white space, or a title/subtitle wraps when the reference does not.

### Root causes

- The authoring slot is inferred from glyph pixels instead of the intended editable text slot.
- A repeated component reuses one global text width even though its icon/divider reservation differs.
- Text fitting uses only `max_lines`; it does not preserve the reference's exact line topology.
- `target_lines` alone is still insufficient when line-height/baseline spacing differs.
- The fit font and the PowerPoint authoring font are not the same resolved face.
- Inner margins, paragraph spacing or line spacing are changed to compensate for a wrong bbox.

### Required evidence

For material text slots record: slot bbox, exact line count, intended line breaks where recoverable, first baseline, baseline delta/line height, paragraph spacing, inner margins, font face/size/weight/color and run boundaries. A text box is not visually accepted merely because it does not overflow.

### Required repair order

1. Recover/reference the intended text-slot bbox and exact reference line count.
2. Repair left/right/top/bottom inner margins.
3. Repair reserved icon/divider/bullet space.
4. Preserve reference line count and intended wrapping.
5. Match baseline spacing/line height and paragraph spacing.
6. Verify the same runtime-resolved font face is used for measurement and authoring, including CJK OOXML binding.
7. Repair weight/color/emphasis runs.
8. Change font size only after geometry is correct.

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
- The parent was represented only by a rectangular bbox, so wave curvature/top-edge profile was not constrained.
- Child elements were positioned against the page rather than the parent visual region.
- Repair moved the child before fixing the parent geometry.
- Local crop selection focused on individual objects and omitted the composed footer/header band.

### Required model

Represent composed systems with a semantic region and relationship evidence:

```json
{
  "object_id": "footer-system",
  "semantic_role": "footer-band",
  "bbox": [0.0, 0.82, 1.0, 0.18],
  "contour_landmarks": [[0.0,0.08],[0.25,0.02],[0.5,0.11],[0.75,0.05],[1.0,0.10]],
  "baseline": 0.74,
  "children": [
    {"object_id":"5g-mark","anchor":[0.50,0.48]},
    {"object_id":"footer-left-copy","anchor":[0.02,0.72]}
  ]
}
```

Landmarks are normalized to the parent bbox. Complex wave/skyline art may be one `imagegen_asset`; readable slogans and brand text remain native above it.

### Repair order

1. Repair parent bbox/top edge/height.
2. Repair contour landmarks/curve profile and skyline baseline.
3. Repair complex background asset scale/crop.
4. Re-anchor foreground children using normalized parent-relative anchors.
5. Repair z-order.
6. Re-render the whole semantic-region crop and then the full page.

## 4. Crop-selection blind spot

Object-only crop selection misses failures that emerge from relationships between objects. Every fixed-reference page should therefore include semantic-region crops in addition to object crops. When content occupies the bottom/top bands, include composed footer/header crops even if no single object spans the band.

The 5-10 crop budget should be diverse: dense text, at least one icon/pictogram cluster, major card/panel geometry, and composed header/footer/brand systems when present. Avoid spending the crop budget on near-duplicate neighboring objects.

## 5. Repair prioritization without a fixed visual threshold

Do not use `score < 0.90` or another universal threshold to decide whether a repair item exists. Rank regions by relative mismatch, material area, semantic importance and explicit issues, then inspect the 3-5 highest-impact regions per iteration. A high scalar score can still hide an obvious icon-identity or anchor defect.

The production state remains `repair-required` while material mismatches are still visible. Numeric metrics are evidence for ranking and regression analysis, not the acceptance authority.

## 6. Title-block geometry drift

### Symptom

Main title, subtitle, section/column headers or small header tags contain the correct words but look optically wrong: sibling spacing differs, the subtitle sits too high/low, a tag crowds the title, or the divider/rule is anchored to the wrong baseline.

### Root causes

- Header text is treated as ordinary body text and repaired with generic TextFit.
- Main title/subtitle/tag/divider are independent page-coordinate guesses rather than one title-block system.
- Only textbox rectangles are compared; first baseline and visible glyph bbox are not.
- Character spacing or font size is changed to compensate for wrong slot geometry.

### Required model and repair

Create a `title-block` semantic region containing independent editable slots for title, subtitle/kicker/tag and any divider. Record each child slot bbox, first baseline, visible glyph bbox/cap-height proxy, sibling gaps and parent-relative anchors. Repair parent title-block geometry first, child slots second, typography third. Never solve a wrong title position by shrinking the font.

## 7. Composite icon/badge drift

### Symptom

A pictogram is recognizable, but the circular/rounded background plate, icon inset, visual center or adjacent label differs from the reference. This is common in four-icon KPI strips and colored roundel systems.

### Root causes

- The plate and pictogram are baked into one loose asset or, conversely, approximated as unrelated objects.
- Placement uses the PNG canvas bbox rather than the alpha-visible bbox and visual centroid.
- The icon is centered mathematically but not optically.
- Readable label text is baked into the image asset.

### Required model and repair

Represent a badge as `plate + pictogram + optional native label`. Record plate center/diameter/radius, pictogram alpha bbox, visual centroid and inset ratio. Anchor the pictogram to the plate center using its visual centroid. Keep readable labels native. Compare and repair the complete badge+label crop, not the icon asset alone.

## 8. Text rhythm beyond exact line count

Exact line count is necessary but not sufficient. Two three-line paragraphs can still differ materially because their first baseline, baseline delta, paragraph spacing, bullet indent or occupied glyph area differs. For dense business slides, Text Slot Preflight must preserve both `target_lines` and `target_line_height`/baseline evidence where recoverable. The authoring engine should prefer slot/baseline correction over font shrink.

## 9. Relationship-first geometry evidence

For repeated columns/cards, record relationships in addition to absolute bboxes: equal column widths, inter-column gaps, header-to-body gap, icon-to-text inset, label-to-badge gap and parent-relative anchors. Responsible Object Repair should repair the owning relationship or parent system once, then propagate to siblings, instead of nudging each child independently. This prevents local fixes from accumulating global drift.
