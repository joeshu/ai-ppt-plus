# Native PPTX object protocol

The layout contract supports four native/editable primitives in addition to
the existing image and text layers.

## Shapes

`slides[].shapes[]` creates a native PowerPoint shape. Use `object_id`,
`type`, `x`, `y`, `w`, and `h`; coordinates follow the deck `units` field.
Supported shape names include `rect`, `rounded_rect`, `oval`, `ellipse`,
`triangle`, `chevron`, `arrow`, `pentagon`, `hexagon`, `parallelogram`,
`trapezoid`, and `diamond`. `fill`, `opacity`, `line`, `line_width`,
`rotation`, and `alt_text` are optional. A `line` is a native PowerPoint
connector/line primitive and is audited as `native_shape` even though
`python-pptx` exposes it as `MSO_SHAPE_TYPE.LINE` rather than
`MSO_SHAPE_TYPE.AUTO_SHAPE`.

## Gradients

Simple deterministic gradients may be declared with:

```json
{
  "gradient": {
    "angle": 90,
    "stops": [
      {"position": 0, "color": "#123456"},
      {"position": 1, "color": "#ABCDEF", "opacity": 0.8}
    ]
  }
}
```

Positions may be fractions from `0` to `1` or percentages from `0` to `100`.
At least two stops are required. Complex, painterly, or irregular gradients
remain image assets and must not be mislabeled as native gradients.

## SVG/vector assets

An `icons[]` entry whose file ends in `.svg` is inserted as an SVG package
part. It is a moveable and replaceable vector asset (`L2`) by default. Set
`vector_editable: true` only when the source and backend guarantee internal
path editing; the manifest then records `L1 editable_vector`. Do not claim
internal path editability merely because a file has an SVG extension.

## Groups

`slides[].groups[]` creates a semantic PowerPoint group while keeping each
child as a separate native shape. The group may include `object_id`, `alt_text`,
`x`, `y`, `w`, `h`, and `children`.

With `children_coordinate_space: "local"`, child coordinates are fractions
inside the group box. Without it, child coordinates use slide coordinates.
Group and child IDs are retained in the object manifest and can be audited or
moved as a unit in PowerPoint.

Formal text must remain in `texts[]`; it must not be baked into a shape, SVG,
or raster asset. The complete brand logo remains a `brand_lockup` asset.

## Tables, charts, themes, and notes

`tables[]` creates an editable native table. It requires `rows`, plus the
usual `object_id`, `x`, `y`, `w`, and `h`. `columns` is optional when the first
row establishes the width. `data_source` is required for authoritative data
in production manifests. The object manifest records a rectangular
`data_snapshot`; the final semantic audit compares native cell values with
that snapshot after applying declared merges.

`charts[]` creates an editable chart from `categories` and `series` data.
Supported types are `column`, `bar`, `line`, `pie`, and `doughnut`. Each
series has a `name` and numeric `values` whose length must equal the category
count; non-finite values are rejected. Record `data_source` and do not invent
values during reconstruction. The object manifest records a canonical
`data_snapshot`; the final semantic audit reads both chart cache data and the
embedded workbook and compares both to that snapshot.

Deck-level `theme` may provide default `font`, `text_color`, and `size` for
native text and tables. Explicit object styles override those defaults.
`speaker_notes` (or `notes`) stores editable presenter notes in the slide's
notes part; notes are not rendered as slide content.

## Master and layout reuse

The composer uses the default PowerPoint template unless a slide selects an
existing layout with `layout_name` or `layout_index`. A deck-level
`theme.layout_name` supplies the default for slides that do not override it.
The selected layout is reused as-is; content remains explicitly positioned by
the layout contract, and unused placeholders are not treated as generated
content. An unknown name or out-of-range index is a blocking error.
