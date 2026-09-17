# Knight fidelity port

This contract incorporates the strongest execution patterns studied from
`knight6669/knight-imagetopptx-skill` at commit
`9265818222fdbdd326410793956ad23a950d72a7`. The upstream project is MIT
licensed. ai-ppt-editable keeps its own authoring, provenance, semantic and
visual gates; these rules strengthen the last-mile reconstruction path.

## Mandatory additions

1. **Full text-slot preflight** — Run `scripts/text_fit_deck.py` against the
   approved layout before authoring. It must measure every visible text path:
   text boxes, text-bearing shapes, table cells, chart titles and rich-text
   runs. The fit report is QA evidence; do not automatically shrink every
   non-fitting target because that can destroy source typography hierarchy.
   Repair geometry/margins first, and only shrink an object when a real render
   confirms overflow.
2. **ImageGen asset route** — Icons, pictograms, decorative art, complex
   illustrations, ribbons and multi-lane/gradient arrow systems are independent
   ImageGen assets with true RGBA. Source crops are reference evidence, not
   final assets, except supplied exact brand marks or an explicit user-approved
   fallback.
3. **Content-aware grid cutting** — Generated sheets declare `ROWSxCOLS` and
   use `slice_grid.py --detect-grid`. Detected row/column centers and midpoint
   edges must be written to the manifest. A count mismatch blocks the sheet.
4. **Visual-centroid repacking and placement** — Square repacking uses the
   alpha-weighted visual centroid and keeps at least 10 px transparent padding.
   For Artifact Tool layouts, set `placement_mode: alpha-centroid-fit` and an
   optional `visual_scale` (for example `0.86` on oversized pictograms), then
   run `normalize_layout_fidelity.py` to convert the visible-content target into
   ordinary authoring coordinates. Edge decorations should stay on `contain`
   unless bleed is explicit.
5. **Native chart gap preservation** — Missing future values must never be
   serialized as zeros. After Artifact Tool authoring, use
   `patch_chart_blank_series.py` to materialize an embedded workbook and shorten
   only the affected series reference. The result must remain a native editable
   chart and pass the native quantitative chart gate.
6. **Physical z-order audit** — Build components in container → icon → text
   order. After saving, run `audit_pptx_layers.py`; inspect the physical XML
   shape tree, not only the python-pptx collection.
7. **Final asset directory hygiene** — Contact sheets and sprite sheets are QA
   evidence, not final slide assets. Run `curate_icon_assets.py` to move them
   out of the final icon directory, then run `validate_transparent_assets.py`.
8. **Local crop QA** — Every dense card, compact non-straight arrow, icon slot,
   table boundary and user-flagged region gets a same-coordinate reference and
   candidate crop. Normalize source and render to the same pixel canvas before
   computing crop or icon metrics.
9. **Effect hygiene** — Flat references must not acquire theme or shape-level
   shadows, glow, reflection or soft edges. Scan the complete PPTX package.

## Commands

```bash
python3 scripts/text_fit_deck.py layout.json \
  --font-file assets/fonts/NotoSansSC-Regular.ttf \
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

The compact run report must list full text-fit coverage, target-fit exceptions,
alpha-centroid placement evidence, native chart gap evidence, transparent-asset
QA, physical layer audit and normalized local-crop evidence. Code generation
without the final render and crop evidence is incomplete.
