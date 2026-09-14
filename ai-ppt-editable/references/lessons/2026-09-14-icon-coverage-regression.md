# Icon coverage regression: task-mtr5y5x6k0wsd

The generated PPTX passed native-object and package audits but its rendered
similarity was low because the reference's right-top smart-home illustration,
five workflow icons, and three card illustrations were replaced by sparse
generic native shapes. This is a visual-fidelity failure, not an editability
success.

For reference reconstruction, PageGraph must inventory every icon and complex
illustration before authoring. Each inventory item requires an independent,
transparent-first ImageGen asset with source-locked silhouette, palette,
bounding box and manifest provenance. Reuse the accepted sheet/cells by hash;
do not create background-color variants. Native shapes remain required for
text, panels, arrows, dividers and simple geometry, but cannot waive asset
coverage or visual-lock thresholds for illustrative regions.

Regression gate: invoke `reference_preflight.py` before the Artifact Tool
marker and after final render. A missing `imagegen-assets-manifest.json`, a
missing PageGraph asset ID, or a region visual-lock failure blocks delivery.
