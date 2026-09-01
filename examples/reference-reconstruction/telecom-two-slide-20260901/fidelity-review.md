# Telecom two-slide fidelity review — 2026-09-01

References:

- `1096b8c3-9374-4c8f-b012-c4a0e93376b9.png` — Part 3, rural/community market
  playbook.
- `48fc317b-aec5-4d05-bd16-d904a2bed4b0.png` — Part 4, rural-market standard
  action.

## Observed gap inventory

| page | reference region | mismatch risk | required repair |
| --- | --- | --- | --- |
| 1 | central three-team framework | high: the halo, three circles and directional arrows carry the visual focus | use one isolated native-ImageGen `complex_art` asset; place all four circle labels as native text |
| 1 | left/right market cards | high: icon silhouettes and red header proportions are easy to drift | use generated icon assets with fixed target bboxes; rebuild card geometry as native shapes |
| 1 | bottom four-principle strip | medium: repeated icon size and baseline alignment | generate the four icons as independent assets; calibrate title/body runs separately |
| 1 | header and footer | high: section title, red rule, Logo lockup and slogan define page identity | reuse complete Logo source; native text; measure title and slogan ink bounds |
| 2 | six-step process row | high: six equal cards need exact spacing and icon centering | generate isolated process icons; keep six cards and connectors native |
| 2 | right key-point rail | medium/high: icon-to-copy rhythm and divider positions | generate the five semantic icons; native text with fixed row heights |
| 2 | three role illustrations | high: crop and subject placement differ visibly | generate three independent 16:9-ish vignettes; record crop/target bbox |
| 2 | product list and bottom slogan | medium: alignment and red emphasis are typography-sensitive | keep all copy native; use explicit runs and locked breaks |
| 2 | bottom-right rural artwork | high: red monochrome gradient and crop are distinctive | use isolated native-ImageGen `gradient_visual`/`illustration`; verify no hard rectangle or white matte |

## Acceptance gates

1. Every row above has an object-level record and an imagegen/source-reuse
   provenance record.
2. No generated asset contains formal copy, a logo, or unverifiable numbers.
3. All visible copy is selectable native text and has measured calibration
   samples for title, cards, diagram labels and footer.
4. Full-resolution side-by-side and overlay reviews show no panel drift, asset
   edge/matte, accidental crop, unexpected wrap or footer collision.
5. The exact source images remain hashed and are not overwritten.

This review is a regression target, not approval metadata. Human visual review
is still required after the PPTX render.
