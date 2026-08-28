# Manifest Registry

`manifest-registry.json` is the canonical cross-manifest index for a run. It does not replace domain manifests: the slide manifest remains authoritative for page intent, the object manifest for semantic objects, asset manifests for extracted/generated assets, and the report index for QA evidence.

The registry normalizes shared identifiers and records the final deck SHA-256. A slide contains `regions[]`, `objects[]`, `text_runs[]`, `asset_ids[]`, and `gate_refs[]`. Assets and objects retain `source_manifest` and raw `details` so older manifests remain compatible. Formal text must be represented by editable text objects; raster assets must not claim to contain formal content.

Build after the slide/object/asset manifests exist with `scripts/manifest_registry.py build`; validate before project or delivery checks with `scripts/manifest_registry.py validate`. `--require-gates` makes the report evidence mandatory.
