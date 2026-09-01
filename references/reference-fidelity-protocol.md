# Reference fidelity protocol

## Scope

Use this protocol for fixed-reference reconstruction when the user asks for
pixel-level comparison, or explicitly requires native image generation for
visual assets. It adds two gates to the normal reconstruction contract:

1. independent visual assets must be generated with the native ImageGen route;
2. formal copy must be rendered as native text and calibrated against measured
   reference ink bounds.

The protocol does not authorize redesign. The reference owns layout, hierarchy,
spacing, palette, crop and visual density. The approved outline or confirmed
transcription owns wording, numbers and facts.

## Asset routing

Classify every non-text visual before authoring:

| class | examples | required route |
| --- | --- | --- |
| `icons` | checklist, people, target, megaphone, chart, handshake | native ImageGen asset sheet or one isolated asset |
| `illustration` | rural scene, people/service vignette, decorative drawing | native ImageGen isolated asset |
| `complex_art` | multi-part framework, halo, glow, artistic composition | native ImageGen isolated asset |
| `gradient_visual` | multi-stop gradient, wave, glow, textured red footer | native ImageGen isolated asset |
| `brand_lockup` | complete logo mark + wordmark | authoritative source reuse only |

When the user specifies native generation, `source_reuse` is forbidden for the
first four classes, even if a generic icon library appears visually similar.
The only exception is an exact supplied asset explicitly approved for reuse.
Complete brand lockups remain a single source-reused object; never regenerate,
slice or redraw them.

Each generated asset record must include:

```json
{
  "asset_id": "slide-01-central-framework",
  "asset_class": "complex_art",
  "source_bbox": [0, 0, 1920, 1080],
  "target_bbox": [690, 245, 580, 500],
  "route": "B4",
  "provenance_mode": "imagegen",
  "generated_source": "generated/slide-01-central-framework.png",
  "copied_to": "assets/slide-01-central-framework.png",
  "prompt_file": "prompts/slide-01-central-framework.txt",
  "backend": "native-imagegen",
  "key_color": "#FFFFFF",
  "alpha_required": true,
  "no_text": true,
  "no_logo": true,
  "style_anchor": "flat corporate infographic, China Unicom red-blue-green-orange",
  "iteration": 1
}
```

`generated_source` is the native ImageGen output. `copied_to` is the exact
asset consumed by the composer. For transparent assets, verify alpha and the
absence of a checkerboard/white matte after compositing. A contact sheet is an
intermediate only: each delivered icon or illustration must remain movable and
must have an individual placement record. Do not ask ImageGen to render formal
Chinese copy, numbers, logos or chart values inside these assets.

## Visual comparison order

Compare reference and render in this order, recording the first failing layer:

1. canvas ratio, outer margins and the red divider/footer geometry;
2. major panel bounds and central focal object;
3. asset silhouette, crop, scale, opacity and z-order;
4. typography metrics, line breaks, color runs and baseline alignment;
5. micro-details such as shadows, corner radii and subtle gradient stops.

Do not hide an asset mismatch behind a higher global similarity score. Require a
full-resolution side-by-side plus a difference overlay for every changed page.

## Typography calibration

Create a `typography-calibration/v1` record for every reference page. At minimum
sample the page title, section title, body/bullet copy, card labels, diagram
labels and footer slogan. Each sample records the exact formal string, source
ink bbox, rendered ink bbox, role, font family/weight, size, color, alignment,
line spacing and locked line breaks. Keep text as native runs; use mixed runs
for red words, numbers and emphasis.

The default release gate is a maximum 12% relative width/height drift per
sample, no unexpected line wrap, no overflow, and no baseline collision. A
font substitution may be accepted only when the measured result passes and the
substitution is disclosed. `shrink_to_fit` is not a calibration strategy: if a
title needs it, repair the font metrics, box, line spacing or explicit break and
rerun the comparison.

## Two-slide regression focus

For the telecom reference pair used in the 2026-09-01 regression, the first
page must separately validate the central three-team framework, both market
cards, their six semantic icons, the bottom four-principle strip, and the
header Logo/section title. The second page must separately validate the six-step
process icons, the right-side key-point rail, the three role illustrations, the
product list, the footer slogan, and the red monochrome rural illustration.

The regression is considered incomplete if any of those groups is represented
by a full-page image, a code-drawn approximation of a complex asset, generated
text, or an unmeasured typography placeholder.
