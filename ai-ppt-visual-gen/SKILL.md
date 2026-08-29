---
name: ai-ppt-visual-gen
description: Generate polished image-format PowerPoint slides or visual intermediates from a topic, approved outline, or content brief. Trigger for “图片版PPT/文生图PPT/AI出图幻灯片/视觉中间稿”, high-information commercial slide images, A1–A5 visual production, page-local image retry, source retention, or deck-strip review. Outputs one raster image per slide plus prompts and generation evidence. It can run standalone or as the visual worker for $ai-ppt-plus. Do not use for editable PPTX reconstruction or deck-wide release; use $ai-ppt-editable or $ai-ppt-plus.
metadata:
 package_revision: 2026.08.29.19
---

# AI PPT Visual Gen

## Boundary and runtime

Create image slides through an executable A1–A5 contract. In standalone mode,
first turn the user's topic/content into a local visual brief and identify any
unverified facts. In orchestrated mode, the supplied outline, formal text,
source references, and design-system revisions are immutable authority.

This skill is independently installable and invokable. Run commands from this
skill directory; every referenced script, reference, schema, template, and test
is contained here. Validate this package before work:

```bash
python3 scripts/validate_skill_package.py --skill-dir .
```

Read `references/visual-generation-tool.md` and
`references/visual-intermediate.md`. Use the runtime-discovered image-generation
tool; do not satisfy image generation with SVG, HTML, Canvas, Pillow drawing,
PowerPoint shapes, or code-added bitmap text.

## Inputs and outputs

Required inputs: topic or approved outline, page count, ratio, audience,
language, presentation context, density, design direction, source references,
formal copy, and reference policy. If formal copy is absent in standalone mode,
create a proposed copy set and mark it `provisional`; never invent authoritative
figures, dates, organizations, quotes, or brand claims.

Required outputs:

- `visual-generation-plan.json`;
- one materialized prompt file and one retained source image per page;
- one project-local copy per page;
- `visual-generation-manifest.json` with hashes, tool/model, and attempts;
- `qa/visual-deck-strip.png` containing every page;
- validation and visual-review status.

The image files may be assembled into an image-only PPTX when requested, but
that artifact is not editable reconstruction and must be labeled accurately.
Use `scripts/compose_image_pptx.py` or the `--image-pptx` option of
`scripts/run_visual_pipeline.py`.

## A1 — Lock production context

Record `generation_context`, canvas, page count, language, audience,
presentation setting, design-system revision, and one density profile:

- `dense` is the commercial/infographic default;
- `balanced` or `minimal` requires an explicit reason;
- use one deck-level palette, surface, type style, icon language, spacing logic,
  and avoid list.

Set `retry_policy.scope` to `single-slide`, normally two attempts and never more
than three. A retry trigger must be observable: failed generation, garbled or
missing approved copy, broken hierarchy, collapsed framework, unsafe content,
or unplanned style drift.

## A2 — Build thick, structured slide plans

Create `visual-generation-plan.json` from
`assets/visual-generation-plan.template.json`. Every non-exempt page must have:

1. one sentence of `core_logic` and one distinct visual framework;
2. an explicit `layout_blueprint` with focal point, reading path, named zones,
   capacity, and anti-template rules;
3. structured `content_model` rather than a list of vague labels;
4. at least three `detailed_content_paragraphs` as planning reserve; these
   paragraphs measure content thickness and are never rendered as extra copy;
5. traceable `formal_text` plus source references;
6. an optional exact-token `keyword_emphasis` map when selected words must keep
   accent colors, including inside the bottom conclusion banner;
7. only approved short `diagram_annotations`; use geometry or icons instead of
   model-invented explanatory labels.

For `dense`, the default capacity baseline is at least four modules, normally
two bullets per module, an introduction, a conclusion, and a KPI/tag layer per
module. If the source cannot support that density, lower the profile with a
reason; never pad with fabricated content.

Framework diversity is enforced deck-wide. Reusing the same card grid or
central-loop composition without a documented reason is a planning defect.

## Reference-image constraints

Every reference declares exactly one treatment:

- `none`: no external visual reference;
- `layout-only`: learn composition, hierarchy, density, reading path, and
  spacing; reject palette, text, data, logos, brand identity, and unique assets;
- `layout-and-style`: only for a user-approved target; learn the above plus its
  palette, surface, typography mood, and icon language, while still rejecting
  reference text, data, logos, and unapproved brand content.

Write `preserve` and `exclude` lists. A reference is visual guidance, never
formal-copy authority. Do not claim “style-only” while copying distinctive
logos, proprietary illustrations, or exact content.

## A3 — Materialize self-contained prompts

Run:

```bash
python3 scripts/materialize_visual_generation_prompts.py \
  visual-generation-plan.json --in-place
python3 scripts/validate_visual_generation_plan.py \
  visual-generation-plan.json --expected-pages N
```

Each prompt must contain the exact ratio, production context, style lock,
focal point, reading path, zone capacities, anti-template rules, reference
treatment, no-invention policy, and every approved visible string verbatim.
Include the exact keyword/color mapping; do not flatten a mapped conclusion to
one color. Keep a formal-text whitelist. Unlisted model text is a defect, not
permission to patch pixels with code.

## A4 — Generate, inspect, and retry one page at a time

For each page:

1. invoke the resolved native raster-generation tool with the materialized
   prompt and only approved references;
2. retain the tool's original generated source and copy it into the project;
3. record prompt path/hash, tool/model, source path/hash, copy path/hash,
   dimensions, ratio, attempt number, and retry trigger in the manifest;
4. inspect full-page legibility, exact visible strings, mapped key-word colors,
   information hierarchy, framework integrity, brand leakage, and fabricated
   content;
5. if the page fails, revise its prompt and regenerate only that page. Never
   invalidate accepted pages or regenerate the whole deck as a convenience;
6. never repair text or decoration by drawing/overlaying code onto the bitmap.

If no compatible image tool is available, record discovery evidence, retry
once with a compatible available model or simplified prompt, then return a
blocked/unavailable state. A wireframe is a separately labeled degraded output
and requires user acceptance.

## A5 — Deck-strip review and handoff

After every manifest-listed page exists, run:

```bash
python3 scripts/build_visual_generation_strip.py \
  visual-generation-manifest.json \
  --output qa/visual-deck-strip.png \
  --expected-pages N --record-in-manifest
python3 scripts/validate_visual_generation_plan.py \
  visual-generation-plan.json --expected-pages N \
  --manifest visual-generation-manifest.json --require-evidence
```

Review the strip for palette/style continuity, density rhythm, framework
variety, title placement, margins, focal-point strength, and accidental page
duplicates. Then inspect each full-resolution page for real text and fine
details. Strip approval never replaces page review, and automated validation
never claims human sign-off.

When called by `$ai-ppt-plus`, return the plan, manifest, strip, approved and
failed slide lists, unresolved copy issues, and hashes. Do not modify editable
PPTX reconstruction artifacts or declare the deck released.

## Blocking conditions

- missing or stale source/prompt/project-copy evidence;
- invented facts or visible text outside the approved whitelist;
- lost keyword emphasis where a mapping exists;
- code-drawn replacement for a real image-generation event;
- retry scope broader than one failed slide;
- missing deck strip or strip that omits a page;
- reference text/data/logo leakage;
- a whole-page image mislabeled as editable PPTX.
