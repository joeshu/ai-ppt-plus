# Reference Fidelity Audit

Reference reconstruction is accepted only when the visible source is mapped
to an editable candidate by object family. A passing PPTX open/render check is
not enough: the audit must explain every recoverable icon, formal text region,
and gradient/complex visual treatment.

## Required mapping

For each page, persist `reference-fidelity/v1` with four linked layers:

1. **Source** — source path, pixel dimensions, SHA-256 and the authoritative
   source bbox for every named region.
2. **Candidate object** — PPTX object IDs, representation type, editability
   level, asset/source hash and geometry in normalized slide coordinates.
3. **Rendered evidence** — the candidate render, visible bbox, named-region
   comparison and review status.
4. **Decision** — accepted, bounded degradation, or blocker, with an owning
   layer and rollback/repair action.

## Icon contract

Every recoverable source icon must have one and only one delivered object. The
record must include `semantic_id`, `source_bbox`, `provenance_mode`, the
delivered asset hash, `pptx_object_ids`, `render_bbox`, `visual_status` and
`placeholder: false`. `provenance_mode` is `source_reuse` or `imagegen`; a
temporary Unicode glyph, letter, number or emoji is not an icon fallback.

The validator must reject missing icons, duplicate frame/icon occurrences,
unresolved asset hashes, empty/incorrect alpha, source icons replaced by
generic symbols, and assets that are not visible in the final render. A logo
lockup remains one complete `brand_lockup` asset and is not OCR'd into ordinary
text objects.

## Typography contract

Each formal text region must carry the exact source string, `source_bbox`, one
or more native PPTX object IDs, and a run-level style map for every change of
color, weight, size, line break or emphasis. At minimum compare title/module/
body scale, boldness, color, line breaks, alignment, margins and ink-box
coverage. A repeated placeholder such as `0` in a numbered process, or a
plain text symbol replacing a source icon, is a blocker when the source is
legible. Text in a brand lockup is governed by the icon/brand contract.

## Gradient and complex-visual contract

Classify each non-uniform region as one of:

- `native_gradient`: at least two explicit color stops, angle and opacity;
- `source_asset`: an independent raster/vector asset with source bbox/hash,
  alpha/edge evidence and render visibility;
- `bounded_degradation`: only when the source cannot be reliably reproduced,
  with a named reason and manual-review requirement.

`flat_fill` is not an implicit fallback for a source gradient. Painterly
backgrounds, glossy 3D rings, brush waves and irregular light effects may be
independent assets, but formal text and simple geometry must remain native and
overlaid. A complex center illustration must never be replaced by unrelated
flat circles merely because the circles are editable.

## Aspect-ratio contract

Compare source and candidate at the same aspect ratio and render scale. If the
delivery policy requires 16:9 while the reference pixels are another ratio,
record the source/candidate ratios, the fit/crop/letterbox mapping and the
protected margins. Silent stretch is a blocker; a deliberate 16:9 fit is a
declared visual exception requiring named-region review.

## Acceptance

Run `scripts/validate_reference_fidelity.py --strict` before composition and
again after rendering. The report is technical evidence, not human sign-off.
The page remains `accept-for-human-review` until a person confirms visual
fidelity, formal text and editability. Repair only the owning layer, rerender,
and compare against both `visual-best` and `editable-best` baselines.
