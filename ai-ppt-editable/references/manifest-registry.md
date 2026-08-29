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
  manifest and optional file hash; `source_ref` should identify the reviewed
  source image or generated input for every file-backed asset;
  `brand_lockup` remains one movable brand asset rather than being converted
  into ordinary text.

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

For panel manifests from older package revisions, `build` falls back to the
manifest-level `source` image when a panel has no per-asset `source_ref`. New
approval and extraction outputs write the per-panel reference directly, so
this compatibility path is only a migration aid.

Coordinate units are part of the contract. When `layout.json` declares
`units: px`, the builder accepts either `[x, y, w, h]`, `{x, y, w, h}`, or the
common top-level `x/y/w/h` region form and keeps those values in pixel space.
The registry text validator uses that same space; it must not apply the
fractional 0–1 check to pixel bboxes.

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
when the report evidence is mandatory; add `--require-asset-hashes` for strict
delivery so every file-backed `AssetSpec` has a current `path_sha256`:

```bash
python scripts/manifest_registry.py validate manifest-registry.json \
  --deck final.pptx \
  --require-gates \
  --require-asset-hashes \
  --report manifest-registry-validation.json
```

The machine-readable schema is
`assets/schemas/manifest-registry.schema.json`; the template is
`assets/manifest-registry.template.json`. The registry is a normalized index,
so a conflict must be fixed in the authoritative domain manifest and the
registry rebuilt, not patched as an undocumented override.
