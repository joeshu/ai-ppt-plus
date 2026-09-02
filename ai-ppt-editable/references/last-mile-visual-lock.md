# Last-mile visual lock

This contract closes the gap between a technically valid editable PPTX and a
visually faithful reconstruction. It is required for every fixed-reference
page after composition and after the final render.

## Required visual-lock records

Create \`visual-lock.json\` with schema
\`ai-ppt-editable/visual-lock/v1\`. Every critical visible region must declare:

- \`region_id\`, \`role\`, \`source_bbox\`, \`render_bbox\`, \`container_id\`,
  \`z_order\`, and \`critical\`;
- \`required_text\` for all legible formal text, with \`exact_once: true\`
  unless the source intentionally repeats it;
- \`style_contract\`: font family/weight/size, text color, alignment, line
  breaks, fill, border, shadow policy and opacity where visible;
- \`provenance\`: source/outline authority, object id, and source hash.

Use explicit roles such as \`title\`, \`title_band\`, \`callout\`,
\`process_step\`, \`panel_title\`, \`footer\`, \`icon\`, \`gradient_art\`,
\`logo\`, and \`background_effect\`.

## Non-negotiable invariants

1. Text must stay inside its declared semantic container. A panel title belongs
   in its title band; a callout sentence belongs in its declared callout box;
   a footer conclusion belongs in the footer region. A valid text object in the
   wrong container is a failure.
2. A declared text-bearing container may not render empty. An empty original
   title band plus a duplicated title elsewhere is a blocker.
3. Every formal string must be visible in the final render and appear the
   declared number of times. Missing, duplicated, clipped or ghosted text is a
   blocker even when XML text exists.
4. Any visible rectangle, banner, shadow, glow, badge, connector or other
   decoration not present in the source must be declared as an approved
   \`added_region\`. Undeclared additions fail the reference route. Do not add a
   second callout box to compensate for a misplaced original callout.
5. A visual asset's semantic meaning is insufficient. Every icon and badge must
   declare a \`style_anchor_id\`, silhouette/style evidence, palette, container
   shape, stroke/fill treatment and \`shadow_policy\`. ImageGen is still the
   required final route for icons, gradients and complex art; generated output
   must match this style contract. If it cannot, retry ImageGen or stop at the
   explicit user fallback decision gate.
6. Typography is measured from rendered ink boxes, not just XML font size.
   Record source/render width, height, baseline and line count for critical text.
   A deviation over 12% in width/height or a line-count mismatch blocks
   acceptance unless a human-approved exception is recorded.
7. Region coordinates are normalized to the source/reference coordinate system.
   Screenshot viewport/capture chrome is excluded from the lock, but source
   geometry and semantic relationships remain authoritative.
8. Visual-best and editable-best remain separate baselines. A raster-heavy
   candidate cannot pass by improving pixels while losing native text/object
   evidence.

## Required final checks

Run after composition and again after the final render:

\`\`\`bash
python3 scripts/validate_visual_lock.py visual-lock.json \
  --report PROJECT/qa/visual-lock.json --strict
\`\`\`

Then inspect the rendered full page and deck strip. The final report must include
all critical regions, missing/duplicate formal text, empty containers, unapproved
additions, icon style mismatches, typography deviations, and the acceptance
state. This report is technical evidence; human visual review is still required.

## Known regression patterns covered by this contract

- panel headers rendered below a blank red header band;
- a footer conclusion omitted while a smaller duplicate remains elsewhere;
- a callout moved into an invented solid box while the source dashed box is empty;
- generated icons changing from flat source icons to shadowed circular badges;
- a serif/light fallback replacing a bold CJK sans title;
- extra shadows, banners or effects lowering source fidelity.
