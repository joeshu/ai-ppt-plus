# Top brand and title fidelity

Header regions amplify small errors because they combine large display type,
brand marks, thin rules and open whitespace. Treat them as a dedicated repair
region instead of relying on whole-slide metrics.

1. Lock the reference crop and measure logo/title/rule boxes in one coordinate
   space. Compare PowerPoint export to the reference whenever possible.
2. Keep formal titles native text. Resolve the closest installed display face,
   then calibrate font size, character spacing, width, baseline and line box.
   Do not replace a formal title with a raster image.
3. Keep official brand artwork as an independent aspect-preserved asset. Native
   ImageGen is for missing decorative artwork, not inventing an official logo.
4. Require transparent safe padding around calligraphy and generated marks;
   visible alpha touching an edge is a repair signal before placement.
5. Align subtitle text and thin rules by measured centerlines. A thin-rule
   mismatch is diagnosed separately from typography so it does not trigger an
   unnecessary title rebuild.
6. Review the same-coordinate header crop at native export scale. LibreOffice
   may rank candidate geometry during iteration, but PowerPoint export decides
   final title wrapping, kerning, baseline and brand placement.

Record remaining mismatches by responsible object: `brand_asset`,
`title_font`, `title_tracking`, `title_baseline`, `subtitle_geometry`, or
`header_rule_geometry`.
