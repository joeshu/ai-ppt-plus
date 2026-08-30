# Visual generation tool contract

This contract is `ai-ppt-plus/visual-generation-tool/v1`. It applies only to
the `visual-creation:image-slide` route and describes how `ai-ppt-plus`
delegates the actual raster-generation event to `ai-ppt-visual-gen`.

## Runtime resolution

Resolve the backend immediately before A4 generation using this order:

1. Use the backend explicitly named by the user.
2. In Codex, prefer the installed `imagegen` tool/skill because it does not
   require an API key and retains the generated source under its runtime
   output directory.
3. In another runtime, use its available native raster image-generation tool
   and record the actual tool name.
4. If no compatible raster tool is available, record
   `visual_intermediate_status: unavailable`, preserve the blocker and stop
   the image-slide gate. Do not silently downgrade to a wireframe.

The selected backend must produce a real raster image. SVG, HTML, Canvas,
Pillow/ImageMagick drawing, a rendered PPTX, or any other code-built picture
does not satisfy this contract. Do not patch or overlay text onto a generated
bitmap with code; repair the production prompt and regenerate the page.

## Required evidence

The plan's `generation_contract` and the manifest's matching top-level fields
must declare:

- `skill: ai-ppt-visual-gen`;
- `tool_resolution: runtime-discovery`;
- `backend_policy: raster-only`;
- `source_retention: generated-source-and-project-copy`;
- `no_code_overlay: true`.

Each slide record then retains the actual `backend`, `model_or_tool`,
`prompt_file`, its SHA-256, original `generated_source`, project `copied_to`, actual returned canvas dimensions and ratio
and image SHA-256 values. The source and project copy must be distinct, fully
decodable raster files with the planned ratio. A plan may request an exact
canvas when the backend supports it, or negotiate a native canvas by declaring
a hard minimum; native-size output must be recorded as-is and is never
silently upscaled. In strict evidence mode, the
manifest also retains a `deck_strip` built from every manifest-listed copied
image; its output hash and source-image hashes are checked against the
manifest. A missing or mismatched record blocks the visual-generation gate.

## Ownership boundary

`ai-ppt-plus` remains the authority for narrative, approved formal copy,
design-system tokens, prompt materialization, evidence, QA and release state.
`ai-ppt-visual-gen` owns the raster-generation event and source
retention only. Generated pixels never become formal text authority. This
contract does not enter or modify the downstream `ai-ppt-editable` /
image-to-editable-PPTX route.

## A3 prompt materialization

Use `scripts/materialize_visual_generation_prompts.py` once the A2 plan and
design system have been reviewed:

```bash
python3 scripts/materialize_visual_generation_prompts.py \
  visual-generation-plan.json --in-place
```

The helper deterministically combines the A1 generation context, visual-only
description, canvas, style lock, layout framework, structured modules, formal
text and reference-treatment rules. When a page has `layout_blueprint`, it also writes
the focal point, reading path, zone capacity and anti-template guards into a
dedicated prompt section; this is the missing spatial contract that keeps a
complex framework from becoming a generic card grid. When a dense page has
`keyword_emphasis`, it writes the approved token-level color map, scope and
treatment into a second prompt section so inline emphasis survives inside a
conclusion banner without introducing copy. When a page needs short
relationship labels inside a framework, A2 may declare `diagram_annotations`
with exact text, purpose, scope and approval; A3 carries only those approved
labels into the prompt. It writes
`prompts/NN-*.md` and the corresponding
`production_prompt` values in the plan. It refuses to overwrite existing
derived prompts unless `--force` is explicit, and supports `--dry-run` for a
preflight. It is intentionally text-only: it does not invoke imagegen,
create PNGs, patch generated pixels, compose PPTX or modify any
image-to-editable-PPTX artifact.

Run the visual-generation validator after materialization. The prompt file
is the exact A3 handoff for A4; if a designer manually revises visual wording,
the complete formal-copy block, text whitelist and anti-fabrication/no-code
policies must remain intact. Extra annotations not present in the whitelist
are not an acceptable way to make a page look denser; use icons, lines and
spatial grouping instead. A keyword color instruction never authorizes new
words: only exact approved tokens may receive the declared color. A diagram
annotation likewise never authorizes an explanatory sentence or invented
metric. Dense pages must also carry an A2 `detailed_content_paragraphs`
reserve; the reserve is used to check content capacity and is explicitly not
rendered as extra page text.

The plan's `retry_policy` is deliberately page-local: allow at most three
attempts per slide (normally two), record the trigger, and regenerate only the
failed page. A successful page and its retained source are not invalidated by
another page's retry.

Reference treatment is explicit. `layout-only` is for the built-in reference
gallery or loose layout inspiration and must reject its palette;
`layout-and-style` is reserved for a user-approved target where palette,
surface and icon language are intentional. Both modes reject reference text,
data, logos and brand leakage. If the page has no reference, use `mode: none`
rather than silently discovering one.

After A4, create and record the A5 deck strip:

```bash
python3 scripts/build_visual_generation_strip.py \
  visual-generation-manifest.json \
  --output qa/visual-deck-strip.png \
  --expected-pages N --record-in-manifest
```

The result is a neutral contact sheet for deck-rhythm review. It is QA
evidence only; it is not a generated slide, a replacement for human review,
or an input to the downstream image-to-editable-PPTX engine.
