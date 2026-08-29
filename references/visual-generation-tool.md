# Visual generation tool contract

This contract is `ai-ppt-plus/visual-generation-tool/v1`. It applies only to
the `visual-creation:image-slide` route and describes how `ai-ppt-plus`
delegates the actual raster-generation event to `GordenImagePPTGen`.

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

- `skill: GordenImagePPTGen`;
- `tool_resolution: runtime-discovery`;
- `backend_policy: raster-only`;
- `source_retention: generated-source-and-project-copy`;
- `no_code_overlay: true`.

Each slide record then retains the actual `backend`, `model_or_tool`,
`prompt_file`, original `generated_source`, project `copied_to`, canvas ratio
and SHA-256 values. The source and project copy must be distinct, fully
decodable raster files with the planned ratio. A missing or mismatched record
blocks the visual-generation gate.

## Ownership boundary

`ai-ppt-plus` remains the authority for narrative, approved formal copy,
design-system tokens, prompt materialization, evidence, QA and release state.
`GordenImagePPTGen` supplies the delegated raster-generation event and source
retention only. Generated pixels never become formal text authority. This
contract does not enter or modify the downstream `GordenImage2PPTX` /
image-to-editable-PPTX route.
