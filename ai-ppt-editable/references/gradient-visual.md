# Gradient visual protocol — R13 baseline

R13 establishes a scene-dependent gradient policy for reference reconstruction. Do not force every gradient into one implementation.

## Routing

1. **B2 `background_blend`** — use for broad, soft, page-level or large-area gradient atmosphere that visually merges with the slide background. This layer may be opaque; alpha is not mandatory when the asset intentionally covers the full slide/background region.
2. **B3 `frame`** — use for a local framework/container whose gradient, glow, wave, light band or complex edge treatment belongs to the frame itself. Generate/extract the frame without text and without B4 elements; preserve transparency when it must overlay other objects.
3. **B4 `element`** — use for independent product images, logos, icons, Wi-Fi waves, decorative marks or other replaceable visual elements. They must remain separate from the B2/B3 layer when independent placement/editability matters.
4. **Native PPT gradient** — use only when the reference can be represented faithfully by a simple deterministic gradient. Do not approximate a complex multi-stop glow/texture with a visibly inferior native rectangle.

## Decision rule

Judge by visual ownership, not by color alone. Ask: does the gradient belong to the whole background, a frame/container, or an independent element? Choose B2/B3/B4 accordingly. A colored disk plus white icon is only one icon scene; it is not a universal protocol.

## ImageGen evidence

When ImageGen is used, record generated source, copied path, layer, prompt file, backend and key color where chroma keying applies. B2 background blends do not require chroma-key alpha when they intentionally cover the background. B3/B4 overlay assets require alpha or another verified compositing method.

## QA

- compare source and final PPTX render at a common size;
- inspect side-by-side, overlay and difference heatmap;
- verify the gradient region does not introduce an unintended hard rectangle, gray band or seam;
- verify B4 elements are not accidentally baked into B2/B3 when they must remain independently replaceable;
- record the route in `gradient-visual-manifest.json` and validate it with `scripts/validate_gradient_visual.py`.

R13 regression case: `存量双终端优秀案例` — broad right-side atmosphere is B2 `background_blend`; product/Wi-Fi elements remain B4 independent assets.
