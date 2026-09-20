# Knight fidelity port

This contract incorporates the strongest execution patterns studied from
`knight6669/knight-imagetopptx-skill` at commit
`9265818222fdbdd326410793956ad23a950d72a7`. The upstream project is MIT
licensed. These rules are part of normal standalone execution; they do not require running Knight side-by-side or any A/B comparator.

## Mandatory execution rules

1. **Full text-slot preflight** — Run `scripts/text_fit_deck.py` against the approved layout before authoring. It must measure every visible text path. Repair geometry/margins first; shrink only after real render evidence confirms overflow.
2. **ImageGen asset route** — Icons, pictograms, decorative art, complex illustrations, ribbons and multi-lane/gradient arrow systems are independent ImageGen assets with true RGBA. Source crops are reference evidence, not final assets except supplied exact brand marks or explicit user-approved fallback.
3. **Content-aware grid cutting** — Generated sheets declare `ROWSxCOLS` and use detected row/column centers. A count mismatch blocks the sheet.
4. **Visual-centroid repacking and placement** — Repack by alpha-visible bbox and alpha-weighted visual centroid with safe transparent padding. Use source visual locks for hard-region replay.
5. **Native chart gap preservation** — Missing future values must never be serialized as zeros. Keep charts native/editable and patch only blank-series references when required.
6. **Physical z-order audit** — Build components in container → icon → text order and inspect the physical XML shape tree after saving.
7. **Final asset directory hygiene** — Contact/sprite sheets are QA evidence, not final slide assets. Quarantine them and validate final transparent assets.
8. **Local crop QA** — Dense cards, compact arrows, icon slots, table boundaries and user-flagged regions get same-coordinate reference/candidate crops.
9. **Effect hygiene** — Flat references must not acquire unintended shadow, glow, reflection or soft-edge effects.
10. **Native geometry locks extend beyond icons** — PageGraph source bboxes are authoritative for stable panels, repeated components, text slots and assets. Repair the owning object before compensating through a neighboring object.
11. **Runtime font parity, not bundled font binaries** — Resolve the real CJK family from the execution environment, materialize an ignored task-local cache only when file-path APIs need it, and use that same face for text-fit and authoring. Chinese runs must set the declared run family and explicit East Asian OOXML typeface (`a:ea`); ai-ppt-editable also keeps `a:cs` aligned. If the requested family is unavailable, fail closed or record an explicit object-scoped fallback decision. Never rely on large checked-in TTF/TTC files as the normal font-delivery mechanism.
12. **Repeated-component and decorative last-mile repair** — Repeated cards, chevrons, title tips and footer art preserve source distribution, not merely object count. Complex art remains an independent asset.

## TextFit Core Conformance

The project absorbs Knight's useful text-fit rules into the canonical
`ai-ppt-editable/scripts/ppt_text_fit.py` and the full-slot
`text_fit_deck.py` audit. The implementation remains runtime-font based and
does not import Knight's Windows-only font path assumptions.

### Tokenization and wrapping

- CJK and other non-Latin characters remain independently wrappable.
- Latin, number, identifier, ratio, date, URL, number+unit and common symbol
  runs stay together whenever the slot permits them. This includes
  `-12.5%`, `+3.2%`, `(2025)`, `5G` and `A/B`.
- A run is split character-by-character only when the complete run is wider
  than the available text slot; a leading over-wide run is handled the same
  way as a later run.
- CRLF, LF and CR explicit breaks are normalized before measuring. Explicit
  breaks are not silently discarded.

### Reference topology and report contract

When a producer declares `target_lines` or `reference_line_count`, the fitter
scans candidate point sizes and selects a result that preserves that exact
line count when possible. A text spec with explicit line breaks also locks the
observed line count unless it declares `allow_reflow: true`. `max_lines` is a
capacity limit and is not treated as reference topology.

Every `best_fit()` result carries `schema: ai-ppt-plus/text-fit/v2` and the
stable evidence fields below:

| Field | Meaning |
| --- | --- |
| `recommended_pt` | Largest measured point size satisfying the requested geometry/topology constraints, or the closest diagnostic result when no full fit exists. |
| `target_pt` | Requested/reference point size, if supplied. |
| `target_lines` | Requested observable line count, or `0` when no topology lock exists. |
| `required_box_px` | Box required by the target size; falls back to the recommended size when no target is supplied. |
| `box_deficit_px` | Positive width/height shortfall against the actual editable slot. |
| `reference_scale` | `recommended_pt / target_pt`, diagnostic evidence only. |
| `line_topology_preserved` | Whether the selected result preserves the requested line count. |
| `geometry_fits` | Whether measured width/height/max-line constraints fit. |
| `repair_hint` | Actionable next repair, such as expanding width/height or preserving topology. |

When a target size is present, the same geometry evidence is also nested under
`target`; recommended-size evidence is retained under
`recommended_required_box_px` and `recommended_box_deficit_px`. This makes the
report unambiguous for Text Coverage and repair tooling.

`text_fit_deck.py` passes reference line evidence into the fitter for native
text, rich runs, table cells, badge/shape labels and chart text. It reports
`geometry_defect_count` and `topology_defect_count` separately. A small
`reference_scale` can prompt review, but it cannot by itself manufacture a
geometry defect or become a production release threshold.

## Commands

```bash
python3 scripts/prepare_runtime_fonts.py \
  --family "Noto Sans CJK SC" \
  --output-dir .runtime/fonts \
  --report qa/font-runtime.json

python3 scripts/text_fit_deck.py layout.json \
  --font-file .runtime/fonts/NotoSansSC-Regular.ttf \
  --report qa/text-fit-all-slots.json

python3 scripts/normalize_layout_fidelity.py layout.json layout.normalized.json \
  --report qa/alpha-centroid-layout.json

python3 scripts/slice_grid.py sheet.png assets/icons --grid 4x5 \
  --detect-grid --square --pad 12 --contact-sheet

python3 scripts/curate_icon_assets.py assets/icons \
  --quarantine-dir qa/contact-sheets --report qa/icon-curation.json

python3 scripts/validate_transparent_assets.py --asset-dir assets/icons \
  --min-padding 10 --report qa/transparent-assets.json

python3 scripts/patch_chart_blank_series.py draft.pptx repaired.pptx \
  --series-index 1 --first-blank-index 7 --report qa/chart-gap.json

python3 scripts/audit_pptx_layers.py repaired.pptx \
  --report qa/pptx-layer-order.json
```

The compact run report must list runtime font evidence, full text-fit coverage, target-fit exceptions, alpha-centroid placement evidence, source visual-lock bbox evidence, native chart gap evidence, transparent-asset QA, physical layer audit and normalized local-crop evidence. Code generation without the final render and crop evidence is incomplete.

## Self-contained acceptance rule

Normal skill execution must succeed without any external comparator. Completion is based on visual inventory, asset classification, ImageGen asset completion, runtime font resolution, text-fit coverage, editable authoring, physical z-order pass, fresh render QA, same-coordinate local-crop QA, responsible-object repair, and final validation. Whole-page SSIM or any other scalar score is diagnostic only unless the user explicitly requests a numeric target. External Knight A/B remains an evaluation harness for skill development, not a runtime dependency.
