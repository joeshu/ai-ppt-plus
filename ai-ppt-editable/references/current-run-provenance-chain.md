# Current-run reconstruction provenance chain

For `reference-reconstruction`, `request_id` is allocated before visual reconstruction and native image generation.

Required fail-closed chain:

`source SHA → request_id → PageGraph provenance → current-run ImageGen assets → deterministic compose → ppt/media exact-byte verification → authoring provenance → delivery_check`

## PageGraph

`page-graph-provenance.json` binds the current `request_id`, source SHA, PageGraph SHA, and producer task `visual-reconstruction`. A graph from another run or whose source/serialized graph bytes changed is rejected before authoring.

## ImageGen assets

When `imagegen-assets-manifest.json` exists, both the manifest and every final asset record must carry the same current `request_id`. Each final asset must declare its SHA-256.

## PPTX media reverse verification

After composition, every approved final ImageGen SHA must appear exactly as bytes in `ppt/media/*`. Substitution, cropping, re-encoding, transformation, or reuse of a different generated asset is rejected when the approved SHA is absent.

This is intentionally an exact-byte rule. A future legitimate transcoding path must provide an explicit deterministic derivation proof rather than weakening the gate.

## Delivery

`validate_authoring_provenance.py` re-runs PageGraph ownership, ImageGen ownership, and PPTX media verification against the delivered deck. Cached validation sidecars are evidence only; they are not trusted as the final authority.
