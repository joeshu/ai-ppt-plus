# Asset Color/Identity Contract

## Purpose

B3 moves icon/illustration identity and color correctness into first-pass generation inputs. It prevents a semantically generic replacement from passing merely because alpha and placement are valid.

This is an asset correctness contract, not a universal visual-score gate.

## Required contract for every `imagegen_asset`

Each ImageGen asset records an `asset_contract` with schema `ai-ppt-plus/asset-identity-contract/v1` and five required dimensions:

1. `semantic_identity` — what the asset depicts, traits that must survive generation, and substitutions that are explicitly forbidden.
2. `contour_traits` — silhouette/shape cues that distinguish the intended asset from a generic icon.
3. `color_roles` — semantic color roles with explicit RGB hex values; roles are included in generation prompts and cache keys.
4. `alpha` — true transparency, transparent edges and safe padding requirements.
5. `provenance` — generation is required and a source crop is not an automatic final fallback.

## Generation integration

`build_imagegen_asset_jobs.py` must propagate the complete contract into each ImageGen job. The stable cache key includes the contract, so changing semantic identity, contour traits, color roles, alpha policy or provenance invalidates stale generated assets.

The generated prompt includes a compact contract suffix describing the required subject, must-preserve identity traits, contour traits, color roles and forbidden substitutions. The original author prompt remains intact.

## Failure classification

Asset QA distinguishes:

- `placement_only` — identity/color/alpha are accepted; only slot position, scale or centroid is wrong. Repair placement without consuming a regeneration attempt.
- `identity_or_color` — subject identity, contour or semantic color roles are wrong. Regenerate only the failing asset.
- `alpha_or_clipping` — transparency, edge contamination, safe padding or clipping is wrong. Repair/regenerate the asset; never substitute a source crop silently.

## Validation

Run:

```bash
python3 scripts/validate_asset_identity_contracts.py PROJECT/authoring-plan.json --json
```

Every `imagegen_asset` must have a complete contract. Missing subject, must-preserve traits, contour traits, color roles, true-alpha requirements or provenance constraints fail closed with stable codes.

## Policy retained

Readable formal text remains native. Generated icons/illustrations remain independent movable assets with genuine RGBA alpha. Source crops are evidence only unless the user explicitly approves a fallback. Placement-only replay must not consume ImageGen regeneration attempts.
