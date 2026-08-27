# Slide object manifest

`slide-object-manifest.json` is the canonical semantic inventory for the
editable deliverable. It is not a second visual layout file: `layout.json`
describes placement, while this manifest describes ownership, editability,
provenance and the expected final PowerPoint object.

Each slide has an `objects[]` array. Every visible or intentionally retained
layer gets a unique `object_id`, `role`, `object_type`, `editability_level`,
`required_for_delivery`, `human_review_required`, and a `provenance` or
`source_ref`. Semantic panels must be separate records and set
`independent: true`; formal text must be `editable_text` and must not be baked
into an image. `traceable_static_graphic`/L3 is the explicit exception for a
complex panel whose border, texture or decoration is kept as one movable asset.

The final deck audit matches object IDs to shape names. Composition helpers
should name pictures and text boxes with the manifest ID, so a manifest claim
cannot silently diverge from the PPTX.
