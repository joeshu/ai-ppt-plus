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
audit goes further and reads the final PPTX object model: formal text must have
a native text container, tables must be native tables, charts must have real
series/cache data and an embedded workbook, and `brand_lockup` must remain one
independent picture. When text and asset manifests are supplied, it also
compares final text exactly and checks embedded media hashes against the
declared source. A semantic mismatch is a technical blocker; human visual
review is still required for appearance and fidelity.

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