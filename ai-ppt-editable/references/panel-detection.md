# Panel candidate detection

`detect_panel_candidates.py` is a proposal stage for reference reconstruction.
It may infer a regular grid from edge projections, but it does not change
`layout.json`, crop assets, or declare a panel approved. Its output is always
`needs-human-confirmation`.

The detector has no default row/column count. For known repeated structures,
pass the expected `--rows` and `--cols` to raise confidence; omit either hint
when that dimension is genuinely unknown. Unconstrained mode proposes only
prominent boundary candidates and uses lower confidence; it must not fill the
slide with an assumed 2×3 grid. A reviewer must still correct full-resolution
`source_bbox` values and exclude non-panel components such as the Logo, intro
bar, footer wave and unbounded gradients. Only an approved candidate manifest
may be passed to `extract_panels.py`.

Approval is explicit and auditable:
`approve_panel_candidates.py candidates.json --approve --reviewer NAME
--revision Rn --output panel-asset-manifest.json`. Use `--bbox` to record a
human correction and `--exclude` to remove a false candidate. The source image
must exist so the approval manifest can carry a SHA-256; extraction rejects a
source mismatch. `extract_panels.py` writes paths relative to the output
manifest directory, so validate the result with `--assets-dir` set to the
project root.
