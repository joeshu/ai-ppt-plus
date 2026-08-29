# Visual intermediate

Read after design-system readiness for layout exploration or reference-led work. Skip only for outline-only delivery, inspection/repair that preserves an already approved visual, an explicit user waiver, or another documented route that does not require visual design. Do not silently use “low risk” to bypass this stage when the user asks for a polished, high-end, premium, executive or brand-specific deck.

Use a visual intermediate to approve composition before PPTX engineering. It owns layout, scale, hierarchy, spacing, color, reading path, focal point, and deck rhythm. It does not own formal copy, numbers, data, or factual claims. This is the `visual-creation` route. It is distinct from `reference-reconstruction`: when the user supplies an approved fixed reference, that reference is the visual authority and the reconstruction route does not require a second generated intermediate. Record the choice and authority in `route-decision.json`; do not silently switch routes because a generated image is convenient.

## Required generation method

Generate the visual intermediate with an image-generation skill, image tool, or multimodal image model. Prefer the installed `imagegen` skill when it is available and follow that skill's generation/edit workflow. Treat each output as a raster design reference for later engineering reconstruction.

The following do **not** satisfy the visual-intermediate stage:

- manually placing PowerPoint text boxes and shapes;
- substituting text into a standard template;
- creating only an HTML, SVG or wireframe layout;
- rendering an already-built PPTX and renaming the render “visual intermediate”;
- inserting a whole generated slide image into PPTX and calling it editable delivery.

Those methods may be used later for PPTX engineering, deterministic diagrams or rapid wireframes, but they must be labeled accurately.

## Visual quality contract

Before generation, translate the approved outline and design system into a production prompt that specifies presentation context, page type, information zones, focal point, reading order, palette, typography scale, material/texture restraint, exact short labels if needed, and explicit avoid items. For example, a “高端大气、国企汇报” request should produce a dignified executive-report composition with disciplined red/navy/neutral or approved brand colors, strong alignment, presentation-scale hierarchy and restrained decoration—not an app dashboard, generic four-card template, poster full of tiny copy, neon HUD or random icon collage.

Judge quality by observable results:

- the page purpose and one-sentence conclusion are visually apparent;
- the primary focal point is unambiguous at meeting-room viewing distance;
- content zones have enough capacity for approved text;
- alignment, whitespace, contrast and typography scale are intentional;
- color and components follow the persisted design system;
- pages generated in the same batch look like one deck;
- no invented chart data, organization names, dates or authoritative facts appear as required content.

If the result is merely functional, generic or aesthetically below the requested level, keep the state at `visual-draft`, revise one visual variable at a time and regenerate. Do not enter reconstruction solely because an image file exists.

Create `visual-intermediate-manifest.json` with `slide_id`, `outline_revision`, `design_system_revision`, `image_path`, `canvas`, `layout_summary`, `focal_point`, `reading_order`, `content_zones`, `reference_images`, `generator_skill`, `model_or_tool`, `prompt_or_recipe`, `quality_target`, `review_status`, `text_authority: none`, and `notes`.

Generate pages in batches of 3–6 with one design system and, where possible, one model/context. Compare the batch as a deck strip before approving individual pages. Rework visual direction before engineering when hierarchy or rhythm is wrong.

Never copy misspellings, pseudo-text, provisional values or invented claims from a generated image into the PPTX. When a reference conflicts with the outline, preserve its spatial relationship and use outline text; log the conflict.

Input: approved outline rows, design system and reference assets. Output: visual files plus manifest and review status. Positive: a comparison page mockup fixes hierarchy while final text remains linked to outline v3. Negative: OCR text from the mockup overwrites approved copy.

Common failures: no image model was actually used, ordinary PPT layout mislabeled as intermediate, generic template appearance, style drift, unreadable hierarchy, distorted reference ratios and invented labels. Validate generation evidence, page purpose, focus, reading order, content-zone capacity, token compliance and deck-strip consistency.

## GordenImagePPTGen-compatible production mode

`visual-creation` has two explicit modes:

| Mode | Use | Text behavior | Required planning |
|---|---|---|---|
| `image-slide` | A generated raster slide should already read like a finished, high-density PPT page | The production prompt includes all approved copy verbatim; generated pixels remain provisional and never override formal PPTX text | `visual-generation-plan.json` plus `visual-generation-manifest.json` |
| `layout-reference` | Explore composition before formal copy is placed | No formal text is required in the generated image; this is the backward-compatible mode | Existing visual-intermediate manifest |

For new image-slide work, borrow the useful A1–A5 discipline from
`GordenImagePPTGen` without changing the downstream reconstruction contract:

- A1 records style, audience, language, page count, ratio and an explicit
  density profile. `dense` is the default; `balanced` and `minimal` require a
  reason so a sparse page is intentional rather than an accidental generic
  template.
- A2 uses `visual-generation-plan.json` to separate `core_logic` and a
  visual-only `visual_generation_prompt` from structured `content_model`.
  Each page selects one visual framework; duplicate frameworks across a deck
  are a blocking planning error unless a future contract adds an exception.
- A3 materializes a self-contained `production_prompt` containing the ratio,
  locked palette, visual hierarchy, explicit no-invention rules and every
  `formal_text[].text` value verbatim. The visual-only prompt is a design
  ingredient, not a runnable image prompt. Use
  `scripts/materialize_visual_generation_prompts.py --in-place` to derive the
  prompt from the reviewed plan; it is a text-only helper and does not call an
  image model or write PPTX files. Manual visual refinements may adjust layout
  wording, but must preserve the generated formal-copy block verbatim.
- A4 records one real raster-generation event per page. The evidence manifest
  retains `generated_source` and `copied_to`, prompt file, backend, model/tool,
  prompt-file SHA-256, canvas and current image SHA-256 values. Both image
  paths and the prompt file are checked during technical validation;
  metadata-only file checks are insufficient.
- A5 compares the generated pages as a deck strip before approving individual
  pages. Build it with
  `scripts/build_visual_generation_strip.py --record-in-manifest`; the helper
  creates only a neutral QA contact sheet from the manifest-listed copied
  images. A visual typo is repaired by regenerating the page prompt/image; it
  is never patched onto the bitmap with code.

The dense content baseline is four or more modules, normally two or more
bullets per module, an introduction, a footer conclusion and at least one
visual KPI/tag layer per module. These are planning capacity checks, not
permission to fabricate data. Every module and formal text item should retain
an outline/source reference. A reference image is layout-only: the prompt
must explicitly reject its text, color and brand leakage.

Validate the contract with:

```bash
python3 scripts/validate_visual_generation_plan.py visual-generation-plan.json \
  --expected-pages N --manifest visual-generation-manifest.json \
  --require-evidence --report visual-generation-validation.json
```

The plan/evidence gate applies only to `visual-creation`. It is not imported
by, and does not alter, the `reference-reconstruction` image-to-editable-PPTX
engine or its asset-extraction rules.

If image generation is unavailable, record the discovery evidence and `visual_intermediate_status: unavailable`; retry once with a simplified prompt or compatible available model. If it still fails, offer a documented placeholder/wireframe only as a degraded artifact, keep it distinct from a visual intermediate, and wait for user approval or report the blocker.
