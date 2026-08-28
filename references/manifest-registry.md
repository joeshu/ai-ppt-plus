# Manifest Registry

`manifest-registry.json` uses `ai-ppt-plus/manifest-registry/v2` and is the
canonical cross-manifest index for a run. It is an integration contract, not a
replacement for domain manifests:

| Concern | Authoritative input |
|---|---|
| page intent and formal content source | slide manifest |
| semantic object plan and editability | object manifest |
| geometry and region decomposition | layout manifest |
| extracted/generated asset provenance | asset manifests |
| QA evidence and gate status | report index and reports |

The registry normalizes these inputs into four shared record families:

- `slides[]` contains `SlideSpec` records with `regions[]`, `objects[]`,
  `text_specs[]`, flattened `text_runs[]`, `asset_ids[]` and `gate_refs[]`.
- `regions[]` contains `RegionSpec` records. Geometry is normalized to a
  `{x, y, w, h}` bounding box or a polygon, and references use arrays so an
  arbitrary number of regions is supported.
- `objects[]` contains `ObjectSpec` records. Every object has a stable ID,
  `object_type`, `editability_level`, provenance and explicit asset references.
  Formal text must use `editable_text`; a raster object may not claim formal
  content.
- `assets[]` contains `AssetSpec` records. Asset paths carry a base, source
  manifest and optional file hash; `brand_lockup` remains one movable brand
  asset rather than being converted into ordinary text.

Every generated v2 record carries `id_origin` (`explicit` or `derived`) so a
missing legacy ID is visible rather than silently dropped. Source manifests
carry SHA-256 evidence, and asset files are checked when a path is present.
The validator catches duplicate IDs, invalid geometry, unresolved region /
object / asset links, text-to-object mismatches, stale source or asset hashes,
and required gate failures. Warnings remain visible for optional evidence such
as an unmaterialized asset file.

The builder accepts historical v1 input shapes, including list bounding boxes
and singular `object_id` / `asset_id` references, and emits v2. A checked-in v1
registry is read for compatibility with a migration warning; rebuild it with
the builder before delivery.

Build after the slide/object/asset manifests exist:

```bash
python scripts/manifest_registry.py build \
  --output manifest-registry.json \
  --project-id PROJECT \
  --deck final.pptx \
  --slide-manifest slide-manifest.json \
  --object-manifest slide-object-manifest.json \
  --layout layout.json \
  --text-manifest text-layout-manifest.json \
  --asset-manifest panel-asset-manifest.json \
  --report-index report-index.json
```

Validate the result before project or delivery checks. Add `--require-gates`
when the report evidence is mandatory:

```bash
python scripts/manifest_registry.py validate manifest-registry.json \
  --deck final.pptx \
  --require-gates \
  --report manifest-registry-validation.json
```

The machine-readable schema is
`assets/schemas/manifest-registry.schema.json`; the template is
`assets/manifest-registry.template.json`. The registry is a normalized index,
so a conflict must be fixed in the authoritative domain manifest and the
registry rebuilt, not patched as an undocumented override.