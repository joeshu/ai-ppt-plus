# Panel candidate detection

`detect_panel_candidates.py` is a proposal stage for reference reconstruction.
It may infer a regular grid from edge projections, but it does not change
`layout.json`, crop assets, or declare a panel approved. Its output is always
`needs-human-confirmation`.

For known repeated structures, pass the expected `--rows` and `--cols` to
raise confidence. A reviewer must still correct full-resolution `source_bbox`
values and exclude non-panel components such as the Logo, intro bar, footer
wave and unbounded gradients. Only an approved candidate manifest may be
passed to `extract_panels.py`.
