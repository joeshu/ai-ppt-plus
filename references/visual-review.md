# Visual review

Read for every rendered page, visual approval, deck consistency gate and human closeout. Input: renders, outline, design system, manifests and reference images. Output: issue log and pass/block decision.

Render every completed page and inspect the raster, not only PPTX XML.

Visual-intermediate checks: verify that an image-generation skill/tool/model actually produced the referenced image; confirm generator, prompt and image path are recorded; reject ordinary PPT/native-shape layouts or PPTX renders mislabeled as intermediates. Check requested style level, hierarchy, whitespace, composition, focal point, reading order, content-zone capacity, design-system consistency and absence of fabricated authoritative data. An existing image file alone is not proof of a passed visual gate.

Page checks after reconstruction: run `scripts/validate_render.py` for page count, minimum dimensions, non-blank pages and known critical regions; then review open/render success, missing content, text clipping, overflow, overlap, off-canvas objects, font substitution, size hierarchy, units/data, image crop, reading order, focal point, and reference-layout relationship. Compare formal wording against the approved outline, never generated intermediate text. The visual gate is diagnostic and does not replace human review or semantic text verification.

If the supplied reference is a phone/WPS/PowerPoint viewer screenshot, treat
black side bars and other capture chrome as `viewer-only`, not slide content.
`reference_audit.py`, `compare_visual.py` and `visual_compare_qa.py` preserve
the raw input and use a validated viewport crop for comparison. This is an
input normalization step; it must never be reported as a PPT layout repair.
For a visible title or module-size concern, use the normalized capture to
populate `typography-calibration.json` and record the font family/metric
assumption separately from the global pixel score.

Deck checks: ratio, typography, palette, component reuse, page rhythm, chart conventions, image treatment, package structure, editable object mix, notes/sources/links, and full-slide flattening.

Record page, code, severity, evidence, owner artifact, proposed fix, and status. Static geometry checks are heuristic; ambiguous overlaps require visual or user review.

Positive: the reviewer flags a likely clipped footnote, fixes the PPTX object and verifies a new render. Negative: XML geometry reports no overlap, so a visibly hidden label is accepted. Common failures are stale renders, source mismatch and per-page approval without deck-strip review; validate render timestamps/hashes and page/deck checklist completion.
