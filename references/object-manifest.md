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

The legacy final deck audit matches object IDs to shape names. The semantic
audit goes further and reads the final PPTX object model: formal text must be a
non-placeholder native text box, tables must be native tables with a non-empty
value snapshot, charts must have real series/cache data, a readable embedded
workbook, and matching source values, and `brand_lockup` must remain one
uncropped top-level picture with no overlapping duplicate text. It also checks
that every visible top-level shape is declared (or explicitly allow-listed),
compares final text exactly, records manifest/deck hashes, and verifies
embedded media hashes against the declared source. A semantic mismatch is a
technical blocker; human visual review is still required for appearance and
fidelity.

Line and connector primitives remain native editable geometry. The semantic
auditor treats both ordinary auto-shapes and `python-pptx` `LINE` shapes as
`native_shape`; do not classify a visible legend line as a raster asset merely
because its runtime shape enum is `LINE`.

The object builder records `data_snapshot` for inline tables/charts and
`source_sha256` for locally available image assets. A production manifest must
retain those fields (or a resolvable `data_source`/source hash); otherwise the
semantic gate cannot prove source identity and blocks the affected object.

Run it directly after the object inventory is reviewed:

```bash
python scripts/semantic_object_audit.py deck.pptx \
  --object-manifest slide-object-manifest.json \
  --text-manifest text-layout-manifest.json \
  --asset-manifest panel-asset-manifest.json \
  --report semantic-object-audit.json
```

`run_pipeline.py` runs this audit automatically whenever a canonical object
manifest is present. It retains `inspect_editable_objects.py` for the simpler
identity/geometry audit, while the semantic report is included in project
quality evidence and blocks the project gate when invalid.

Use `scripts/build_object_manifest.py layout.json --panel-manifest
panel-asset-manifest.json --output slide-object-manifest.json` to create the
initial inventory. Review Logo and other authoritative brand assets before
accepting the generated roles; the builder is a deterministic baseline, not a
visual recognition model.

After the object inventory is reviewed, use
`scripts/build_slide_manifest.py layout.json --object-manifest
slide-object-manifest.json --output slide-manifest.json` to create the
project-level slide manifest. Supply the confirmed reference and formal
content sources; this adapter does not create human approval or sign-off.
