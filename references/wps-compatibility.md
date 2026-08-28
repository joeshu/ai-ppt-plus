# WPS compatibility profile

Use this profile when the target environment is desktop WPS and iPhone WPS.
Microsoft YaHei is the preferred layout font only when it is already licensed
and available on the target device. The bundled Noto Sans CJK SC file is the
legal local-render fallback; it is not a claim that WPS will use that font on a
device unless the PPTX embeds it or the device has it installed.

The profile has three independent evidence signals:

1. `declared_font`: the task declares a concrete family and local font asset.
2. `resolved_font`: the task-local probe resolves that family and verifies the
   representative CJK glyph set.
3. `render_visible`: the final PPTX, not a pre-render image, is rendered with
   the task-local font directory and passes the non-blank visual gate.

For strict release, also provide a completed copy of
`assets/wps-target-review.template.json` with both `devices.desktop_wps` and
`devices.iphone_wps` set to `true`. A sidecar font directory is not an embedded
font. If `inspect_pptx.py` does not verify OOXML embedded font declarations,
relationships and parts, strict release remains blocked.

Run the combined gate with:

```bash
python3 scripts/validate_font_delivery.py \
  --font-report font-report.json \
  --font-asset-report font-asset-validation.json \
  --inspection inspection.json \
  --render-report render-report.json \
  --render-visual-gate render-visual-gate.json \
  --target-review wps-target-review.json \
  --profile wps --require-embedded --require-target-review \
  --report font-delivery-validation.json
```
