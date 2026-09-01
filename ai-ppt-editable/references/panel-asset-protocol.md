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

Before removing a whole-frame asset, inventory every non-panel component it
contains (overview badges, intro bars, footer waves and decorative lines). Each
component must be re-homed as a native shape or independent asset; deleting the
frame must never silently delete content.

Use `extract_panels.py` with full-resolution `source_bbox` values to produce
panel files. Do not crop from a palette thumbnail or guessed scaled coordinates.
The emitted manifest records actual asset sizes and writes each `file` relative
to the manifest directory (for example, `panels/panel-01.png`), so the same
manifest can be checked with `validate_panel_assets.py --assets-dir PROJECT`.

## Manifest

Record each panel in `panel-asset-manifest.json` with `panel_id`, `file`,
`sha256`, `source_bbox`, `editability_level`, `treatment`, `text_layer_ids` and
`raster_text_audit`. The audit must be `verified-clear` for a text-free substrate
or `verified-excluded` when native text is placed above it; a bare
`formal_text_baked_in: false` declaration is insufficient. The six
containers in a six-card reference therefore produce six entries, not one
`frame` entry. If a whole-frame asset remains, record the exact non-semantic
regions it covers and why it does not prevent panel movement.

For any independent asset, `source_bbox` is the full placed asset region in
the source coordinate system, including intentional transparent or background
padding. A sub-element bbox (for example, only the red symbol inside a full
Logo wordmark) is not valid evidence for the full asset placement.

## Gate

Before composition, run `validate_panel_assets.py --require-independent` and
`validate_image_to_editable_contract.py --strict` for a fixed-reference route.
Missing panel entries, duplicate panel files, overlapping panel ownership or
formal text baked into a panel image are repair items; in strict mode they block
delivery. Missing `raster_text_audit`, unresolved `text_layer_ids`, or any
flattened full-slide object also block delivery. For strict release, also pass
`--require-hashes`; `sha256` must be the hash of the independent panel file
named by `file`, while `source_sha256` remains the hash of the original
full-resolution reference.
