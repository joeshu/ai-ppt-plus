# Independent panel asset protocol

## Rule

Repeated cards, columns, tiles, modules and bordered information containers are
semantic layout units. Each must be independently movable in the editable deck.
Do not place six cards into one full-slide `frame.png` merely because their
borders were generated together.

## Treatment

- **Simple card**: prefer native PowerPoint rounded rectangle/line/fill shapes;
  keep border, fill, shadow and header band editable when practical.
- **Complex card**: use one transparent image asset per card, with the card's
  full border/background/header decoration but no formal text; keep text as
  native text boxes above it.
- **Pure background**: gradients, light effects and non-semantic waves may stay
  in the background layer.
- **Brand/logo**: keep the authoritative logo asset separate from card frames.

## Manifest

Record each panel in `panel-asset-manifest.json` with `panel_id`, `file`,
`source_bbox`, `editability_level`, `treatment` and `text_layer_ids`. The six
containers in a six-card reference therefore produce six entries, not one
`frame` entry. If a whole-frame asset remains, record the exact non-semantic
regions it covers and why it does not prevent panel movement.

## Gate

Before composition, run `validate_panel_assets.py --require-independent`.
Missing panel entries, duplicate panel files, overlapping panel ownership or
formal text baked into a panel image are repair items; in strict mode they block
delivery.
