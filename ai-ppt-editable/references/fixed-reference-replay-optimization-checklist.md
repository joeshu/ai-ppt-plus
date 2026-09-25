# Fixed-reference replay optimization checklist

This checklist is the closeout record for dense image-to-editable-PPTX pages
with repeated icons, brand artwork and a chart. It is intentionally reusable;
it is not a visual score threshold.

## Before composition

- [ ] Freeze source path, dimensions, aspect ratio and SHA-256.
- [ ] Inventory every non-text visual: each icon, badge, brand mark, footer
      wave/skyline, 5G mark, ribbon and decorative effect. Give each a stable
      `visual_id` and `asset_id` with a normalized source bbox.
- [ ] Classify each object once: formal text/data and reliable ordinary
      geometry remain native; pictograms, brand art and decorative artwork use
      native `image_gen.imagegen` final assets.
- [ ] Require a real native-tool receipt before authoring. A filename or
      `backend: native-imagegen` string alone is not evidence.
- [ ] For compatible icon sheets, record the generation batch, slice roster,
      alpha-trim transform and independent final paths. Never deliver the
      contact sheet itself.
- [ ] Record icon foreground, internal detail and host colors from each source
      crop before the first ImageGen prompt; white-on-red and red-on-white are
      different assets, even when their pictograms share one silhouette.

## Asset QA

- [ ] Validate RGBA alpha, visible bbox, centroid, transparent corners,
      clipping and local-crop identity/color for every independent asset.
- [ ] Keep generated raw output and the delivered derivative separately; record
      any wide-band crop/resize transform.
- [ ] Generate every brand-class final asset with native ImageGen, whether the
      reference is a screenshot crop or an official standalone file. Use the
      source only as prompt/geometry/color evidence. Never trace it with native
      shapes or use the source crop as the final asset.
- [ ] Keep formal copy that sits beside/over the art native and keep every
      generated visual independently movable and replaceable.
- [ ] Run `scripts/validate_icon_color_roles.py` on the final icon PNGs, then
      review each icon inside its actual slide background at presentation size.

## Authoring and closeout

- [ ] Bind asset IDs to the authoring plan/layout and preserve stable picture
      names in the PPTX.
- [ ] For charts with unverified workbook data, preserve visible topology and
      labels with editable line/marker primitives; do not invent a native chart
      or add values that are absent from the reference.
- [ ] Transcribe every visible series into a point ledger before drawing. Record
      the month, displayed label and exact endpoint; a current-year partial
      series ends at its last visible month. Name the point, segment and label
      primitives, then run `scripts/validate_reference_chart_series.py` against
      the final PPTX. Inspect overlapping labels in a chart-only render crop.
- [ ] For rounded panels, use a bounded corner size. Some authoring libraries
      interpret `rectRadius` in slide units rather than source pixels, turning
      broad cards into near-ellipses. Prefer a plain rectangle when that option
      cannot be calibrated; check every broad card silhouette in the first
      rendered draft.
- [ ] Bind the task-local CJK fonts to the actual renderer and require a fresh
      render receipt with `fontconfig_bound=true` and a non-empty font hash.
- [ ] Render once, inspect the full page plus 5–10 diverse risk crops, then
      repair the owning object/relationship. Do not regenerate the whole page
      for a placement-only defect.
- [ ] For each repeated table, compare source and render row labels, value
      columns and highlighted results. Do not combine factor rows to save room.
- [ ] Check small relationship marks such as plus signs between benefit cards
      and label rails beside case text; they encode meaning beyond OCR.
- [ ] Inspect title/subtitle and brand/footer crop after merging reused pages.
      A matching source hash does not waive this final visual review.
- [ ] Compare dense copy with source transcription; flag unreadable source
      spans and remove unsupported explanatory copy.
- [ ] Preserve numbered clauses and secondary prompts in dense measure rows;
      compare the source row crop and final row crop after text fitting, rather
      than simplifying the copy merely to clear an overflow warning.
- [ ] Mark every colored/bold run inside dense source copy, rebuild those as
      editable PowerPoint character runs, and inspect the rendered line breaks.
- [ ] Treat a colored/bold lead phrase plus same-line body as one line-layout
      contract. Do not put the body in a narrow residual box and let `shrink`
      solve it: measure both spans, keep a shared baseline, and move only the
      continuation to a full-width next line when the combined line is too
      wide. Reject runs whose body font becomes visibly smaller than adjacent
      paragraphs.
- [ ] Split composite product art into independently movable semantic assets
      whenever the source shows distinct product families (for example, phone
      and FTTR hardware). A combined generation sheet is an intermediate only;
      final placements require separate picture objects and stable asset IDs.
- [ ] For standard widescreen output, set the page to exactly 13.333333 × 7.5
      inches and scale source pixel coordinates independently on X and Y. Do
      not infer slide size from the reference image's pixel dimensions alone.
- [ ] Run source-visual coverage, object/editability, package integrity and
      no-whole-slide-raster gates.
- [ ] Run the post-export embedded-media byte gate. Every manifest `asset_id`
      must match at least one `ppt/media/*` hash in the delivered PPTX; repeated
      placements may share one hash.

## Efficiency guardrails

- [ ] Batch only compatible simple alpha icons; dedicate calls to brand
      lockups, calligraphy, wide bands and complex art.
- [ ] Retry only failed asset IDs. Reuse only when source hash, prompt/cache
      key, delivered hash, alpha QA and local-crop QA all match.
- [ ] Keep one candidate plus bounded repair candidates for a one-page run;
      use regional crops and responsible-object repair instead of page-wide
      rebuilds.
- [ ] Emit a compact difference report that names the owning object, evidence,
      decision and next repair—never hide a salient icon/brand mismatch behind
      one global similarity score.
