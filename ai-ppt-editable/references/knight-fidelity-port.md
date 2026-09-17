# Knight fidelity port

This contract incorporates the strongest execution patterns studied from
`knight6669/knight-imagetopptx-skill` at commit
`9265818222fdbdd326410793956ad23a950d72a7`. The upstream project is MIT
licensed. ai-ppt-editable keeps its own authoring, provenance, semantic and
visual gates; these rules strengthen the last-mile reconstruction path.

## Mandatory additions

1. **Text-slot preflight** — Run `scripts/ppt_text_fit.py` for every visible
   text-producing path, including rich-text runs, table cells, badges, metrics,
   chart labels and manually composed number/unit lines. Preserve the source
   line count. If `reference_scale < 0.90`, repair box geometry, margins, icon
   reservation or wrapping before accepting a smaller font.
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
   Final icon records use `placement_mode: alpha-centroid-fit` when transparent
   canvas padding or asymmetric silhouettes would otherwise shift the subject.
5. **Physical z-order audit** — Build components in container → icon → text
   order. After saving, run `audit_pptx_layers.py`; inspect the physical XML
   shape tree, not only the python-pptx collection.
6. **Local crop QA** — Every dense card, compact non-straight arrow, icon slot,
   table boundary and user-flagged region gets a same-coordinate reference and
   candidate crop. An arrow plus its label is one QA component.
7. **Effect hygiene** — Flat references must not acquire theme or shape-level
   shadows, glow, reflection or soft edges. Scan the complete PPTX package.

## Commands

```bash
python3 scripts/ppt_text_fit.py --text="看 diff、看运行结果" \
  --box 980x42 --font "Microsoft YaHei" --target-pt 22 --max-lines 1

python3 scripts/slice_grid.py sheet.png assets/icons --grid 4x5 \
  --detect-grid --square --pad 12 --contact-sheet

python3 scripts/validate_transparent_assets.py --asset-dir assets/icons \
  --min-padding 10 --report qa/transparent-assets.json

python3 scripts/audit_pptx_layers.py output.pptx \
  --report qa/pptx-layer-order.json
```

The compact run report must list text-fit coverage, rejected/exception objects,
transparent-asset QA, physical layer audit and local crop evidence. Code
generation without the final render and crop evidence is incomplete.
