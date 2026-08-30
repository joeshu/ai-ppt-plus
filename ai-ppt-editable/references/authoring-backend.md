# PPTX Authoring Backend

`scripts/compose_pptx.py` is the stable CLI entrypoint. It coordinates the
workflow and keeps the historical command-line options; it is not the place
for object-level implementation.

The implementation is split into focused modules:

| Module | Responsibility |
|---|---|
| `component_expander.py` | deck normalization, component instances and layout selection |
| `pptx_primitives.py` | native text, shapes, groups, tables, charts and typography |
| `asset_placement.py` | background/frame/panel/icon placement and SVG package replacement |
| `preview_renderer.py` | optional Pillow preview rendering and preview font selection |
| `atomic_output.py` | sibling temporary files, atomic replacement and ZIP rewrites |
| `authoring_backend.py` | `python-pptx` backend orchestration and optional font embedding |
| `embed_fonts.py` | licensed PresentationML font post-processing |

The backend order is fixed for reconstruction fidelity:

1. background and whole frame;
2. independent panels;
3. native shapes, groups, tables and charts;
4. speaker notes;
5. icons and SVG assets;
6. editable text.

Independent panel images are structural substrates. They must be inserted
before native overlays so badges, legend keys, bullet marks and other simple
geometry remain visible and independently editable. The Pillow preview
renderer follows the same order; a preview that disagrees with the PPTX
layering is a QA defect, not a harmless approximation.

The default family is `Noto Sans CJK SC`, matching the bundled
`assets/fonts/NotoSansSC-Regular.ttf`, not Microsoft YaHei. A task may
override it through the deck theme or an explicitly licensed font. Font
availability, CJK coverage and delivery embedding remain separate gates; this
module does not claim delivery merely because a font name was written into a
run.

Every PPTX, preview, render report, font report and manifest emitted by the
authoring path is first written to a sibling temporary file. `atomic_replace`
flushes the completed file before rename and never deletes the previous
artifact before replacement. SVG conversion files are registered by the
placement layer (`svg_to_png(..., temporary_files=...)`) and removed in a
`finally` cleanup. When SVGs are present, the native SVG rewrite happens on the
temporary package before the final output is published, so a failed rewrite
does not replace an existing PPTX with a partial result.

`preview_renderer.py` is an authoring diagnostic only. The rendered PPTX is
the visual source of truth; when previews are retained, compare them with
`scripts/validate_preview_consistency.py` and record the metric report. For
delivery-bound reconstruction, use `compose_pptx.py --strict-input`: missing
primitive types, unsupported text alignment, clipped boxes and malformed
coordinates fail authoring instead of being silently normalized.

The backend preserves the existing `compose_pptx.py` CLI and the compatibility
imports used by manifest builders. R13 remains a frozen regression fixture;
this split changes ownership and testability, not the reconstruction contract.
