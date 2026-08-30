---
name: ai-ppt-visual-gen
description: Generate polished image-format PowerPoint slides or visual intermediates from a topic, approved outline, or content brief. Trigger for “图片版PPT/文生图PPT/AI出图幻灯片/视觉中间稿”, high-information commercial slide images, A1–A5 visual production, page-local image retry, source retention, or deck-strip review. Outputs one raster image per slide plus prompts and generation evidence. It can run standalone or as the visual worker for $ai-ppt-plus. Do not use for editable PPTX reconstruction or deck-wide release; use $ai-ppt-editable or $ai-ppt-plus.
metadata:
 package_revision: 2026.08.30.07
---

# AI PPT Visual Gen

## Boundary and runtime

Create image slides through an executable A1–A5 contract. In standalone mode,
first turn the user's topic/content and mixed source notes into a local
`PPT思路表` draft, identify unverified facts, and stop for owner review. In
orchestrated mode, the supplied approved table, formal text, source references,
and design-system revisions are immutable authority.

This skill is independently installable and invokable. Run commands from this
skill directory; every referenced script, reference, schema, template, test and
the pinned `requirements-ci.txt` are contained here. Validate this package
before work:

```bash
python3 scripts/validate_skill_package.py --skill-dir .
```

Read `references/visual-generation-tool.md`,
`references/visual-intermediate.md`,
`references/outline-thought-table.md` and
`references/rendered-slide-qa.md`. Use the runtime-discovered image-generation
tool; do not satisfy image generation with SVG, HTML, Canvas, Pillow drawing,
PowerPoint shapes, or code-added bitmap text.

## Inputs and outputs

Required inputs: topic or an approved PPT thought table/outline, page count, ratio, audience,
language, presentation context, density, design direction, source references,
formal copy, and reference policy. If only a topic or unapproved draft is
available in standalone mode, create the thought table and stop for review;
never invoke image generation from it. Never invent authoritative figures,
dates, organizations, quotes, or brand claims.

Required outputs:

- `visual-generation-plan.json`;
- reviewed `PPT思路表.xlsx|csv` plus narrative-gate evidence;
- one materialized prompt file and one retained source image per page;
- one project-local copy per page;
- `visual-generation-manifest.json` with hashes, tool/model, and attempts;
- `qa/visual-deck-strip.png` containing every page;
- validation and visual-review status.

The image files may be assembled into an image-only PPTX when requested, but
that artifact is not editable reconstruction and must be labeled accurately.
Use `scripts/compose_image_pptx.py` or the `--image-pptx` option of
`scripts/run_visual_pipeline.py`.

## O0–O4 — PPT 表格思路法（生图前置闸门）

The first product is not a slide image. It is a reviewable thought table built
from all supplied sources: project initiation material, prior special reports,
project explanations, meeting notes and discussion fragments.

1. **O0 source sweep** — inventory every source, authority, conflict, missing
   fact and `待验证` item.
2. **O1 first draft** — create `PPT思路表.xlsx` or `.csv`. The user-facing
   minimum columns are `页码`, `标题 / 核心思想`, `页面大纲` and `我的修改意见`.
   The first three columns are drafted by AI; the fourth is reserved for the
   user's verbatim notes. Add governance columns such as `status` and
   `data_sources` when available.
3. **O2 owner review** — the user writes fast structural comments such as
   “提前/后移”“拆开”“降低技术性”“突出业务价值”. The notes are never
   silently summarized, discarded or used as permission to invent copy.
4. **O3 narrative revision** — create a new outline revision from the notes;
   preserve the original table, owner notes and a change log. Re-check page
   order, one-sentence conclusion, page purpose, business value and removable
   content.
5. **O4 approval** — only when every formal row is `approved`, key facts are
   sourced, the page roster is continuous and the owner approval metadata is
   recorded may the plan enter A1–A5. Run:

   ```bash
   python3 scripts/validate_outline_table.py PROJECT/outline/PPT思路表.xlsx \
     --require-approved --report PROJECT/qa/outline-validation.json
   ```

   The plan records this decision in `narrative_gate`. A missing, stale,
   unapproved or hash-mismatched table blocks materialization and generation.
   In standalone topic mode, return the draft table and remain at O2/O3; do
   not make a visual draft merely because the topic is clear.

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
unreadable hierarchy, or unplanned style drift. Also lock `generation_session`
to one model/context and `quality_target.tier` to `premium-commercial` (or an
explicitly approved enterprise-commercial profile). “豪华/高端” must become
observable composition, typography, material, spacing and commercial-safety
rules.

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
   accent colors, including inside the page's conclusion or action close;
7. only approved short `diagram_annotations` with an approval source; use geometry or icons instead of
   model-invented explanatory labels.
8. a `copy_contract` with `render_authority: render_copy`, a deduplicated
   `render_copy` list, `exact_once: true`, and a page-appropriate character
   budget. `content_model` is layout-slot metadata; `formal_text` is source
   authority. Neither may become a second visible-copy list.
9. a `representation_policy` stating that each primary relationship has one
   visual encoding, and that secondary elements may add meaning but may not
   repeat the same steps, conclusion, or summary in another numbering system.

The plan must also carry:

- `narrative_gate`, pointing to the exact approved thought-table file and its
  SHA-256;
- `quality_target`, including premium-commercial requirements, presentation-
  scale text sizes, copy-density guidance and commercial-safety policy;
- `generation_session`, including a session ID, same-model/context policy,
  batch size, style anchor and shared preamble;
- `closure_treatment` per slide when the page has a conclusion or action
  close. This controls whether that copy is inline, integrated into the
  diagram, placed in a side rail, shown as a compact callout, or omitted as a
  separate visual element. A semantic conclusion field is not permission to
  impose a full-width bottom banner on every page;
- `canvas_policy`, which separates a preferred canvas from a hard minimum.
  Set `require_exact_dimensions: true` only when the selected backend is known
  to support the requested pixel size. For native image backends, keep the
  planned ratio, record the actual returned dimensions, enforce the declared
  minimum, and emit a native-resolution warning when the backend returns a
  smaller but still presentation-safe canvas. Never silently upscale or claim
  exact-size evidence that the backend did not produce.

For new image-slide plans, validate the two anti-regression contracts with:

```bash
python3 scripts/validate_visual_generation_plan.py visual-generation-plan.json \
  --expected-pages N --require-copy-contract
```

The copy budget is measured on unique visible strings and total characters, not
on duplicated declarations in the planning model. If it is exceeded, merge,
shorten or split content before generation; do not solve the problem by making
Chinese text smaller.

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
treatment, no-invention policy, every approved visible string verbatim, and
the page-level closure treatment. Treat `footer_banner` as a semantic content
field, not a layout command; materialization must not turn it into a fixed
bottom banner by default.
Include the exact keyword/color mapping; do not flatten a mapped conclusion to
one color. Include the narrative gate, continuous-generation lock, premium
commercial quality target and language policy. Use the `render_copy` list as
the only visible-copy authority: render each item at most once. Keep
`formal_text` in the prompt as an audit/source anchor only, explicitly marked
“do not typeset again”; keep content-slot metadata free of repeated exact
sentences. Unlisted model text is a defect, not permission to patch pixels
with code.

## A4 — Generate, inspect, and retry one page at a time

For each page:

1. invoke the resolved native raster-generation tool with the materialized
   prompt and only approved references;
2. retain the tool's original generated source and copy it into the project;
3. use `scripts/register_generated_slide.py` to perform the untouched project
   copy and record prompt path/hash, tool/model, source path/hash, copy
   path/hash, actual dimensions, ratio, generation session ID,
   context-continuity status, attempt number, and retry trigger in one atomic
   handoff; use `--force` only for the failed page's explicit retry;
4. inspect full-page legibility, exact visible strings, mapped key-word colors,
   information hierarchy, framework integrity, brand leakage, fabricated
   content, and whether the lower third is being forced into a repeated bar
   that the page plan did not request;
5. if the page fails, revise its prompt and regenerate only that page. Never
   invalidate accepted pages or regenerate the whole deck as a convenience;
6. never repair text or decoration by drawing/overlaying code onto the bitmap.
7. if the runtime cannot preserve the same model/context, retain the project
   style anchor and mark continuity as degraded; strict commercial generation
   remains blocked until an approved exception is recorded.

When a slide declares `visual_assertions`, run the readback gate after the
image exists. `must_contain_text` / `forbidden_text` use OCR against the
retained project copy; `keyword_emphasis` must pass both OCR readback of the
declared token and pixels near the declared color (optionally inside a
normalized `region`); `min_ink_ratio` catches an empty or nearly empty page.
`region` is `[x, y, width, height]` in normalized page coordinates, not corner
coordinates. Set `ocr_failure_policy` to `block` when OCR evidence is a hard
delivery requirement, or `manual-review` when the requested language pack is
not guaranteed in the runtime. Manual-review mode may continue image/PPTX
assembly only when pixel-color and ink gates pass; it must emit a warning,
retain the OCR capability error, and keep human closeout/release pending.
An available, trusted OCR engine that actually misses required text remains a
blocker. For populated panels or action slots, add explicit placeholder tokens
such as `placeholder`, `Lorem`, `待补充`, `示意文字`, and context-specific
standalone ellipses to `forbidden_text`; never accept empty bullets as content.
Use `readback_scope: all-render-copy` when every approved visible string
matters. The assertion runner expands that scope to the complete deduplicated
render list, so omitted or rewritten sentences are caught instead of being
hidden by a title-only smoke check. If OCR is unavailable, keep the page at
manual review; do not report exact-copy compliance from a technical pass alone.

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
  --manifest visual-generation-manifest.json --require-evidence \
  --require-narrative-approval --require-copy-contract
```

If any page declares post-generation assertions, the visual pipeline also
runs:

```bash
python3 scripts/validate_visual_assertions.py \
  visual-generation-plan.json --manifest visual-generation-manifest.json \
  --expected-pages N --report qa/visual-assertions.json
```

The executable worker wrapper bounds every evidence subprocess and retains
per-step logs. Review the strip for palette/style continuity, density rhythm,
framework variety, title placement, margins, focal-point strength, accidental
duplicates, competing encodings of one relationship, missing/rewritten copy,
and closure diversity. A repeated bottom bar is a defect unless the approved
design system explicitly calls for it. Strip approval never replaces page
review, and automated validation never claims human sign-off.
Override the default 600-second limit with
`run_visual_pipeline.py ... --timeout-seconds N`; a timeout or spawn failure
is recorded as a blocked step with its captured output.

When called by `$ai-ppt-plus`, return the plan, manifest, strip, approved and
failed slide lists, unresolved copy issues, and hashes. Do not modify editable
PPTX reconstruction artifacts or declare the deck released.

## Blocking conditions

- missing or stale source/prompt/project-copy evidence;
- missing, unapproved or stale PPT thought-table evidence;
- missing same-model/context continuity evidence;
- missing premium-commercial quality profile or canvas-dimension compliance;
- invented facts or visible text outside the approved whitelist;
- lost keyword emphasis where a mapping exists;
- code-drawn replacement for a real image-generation event;
- retry scope broader than one failed slide;
- missing deck strip or strip that omits a page;
- reference text/data/logo leakage;
- a visible-copy contract that duplicates, omits, or exceeds its character budget;
- two competing visual encodings for the same relationship or conclusion;
- a whole-page image mislabeled as editable PPTX.
