# Visual closeout evidence gate

Use this gate after the final fresh render and same-coordinate crop review. It
does not define an SSIM or pixel threshold. It prevents a human closeout from
contradicting its own evidence.

The visual authority is the fresh LibreOffice+Poppler render produced with the
same task-local fonts used for fitting. Artifact Tool preview/import output is
structural diagnostic evidence only and cannot close visual review. A preview
font-rendering discrepancy must be recorded once and must not trigger a PPTX
repair when the authoritative render and object audit are complete.

Start from `assets/visual-closeout.template.json`. Cover these semantic roles,
using multiple regions when needed: `brand`, `title_typography`,
`primary_structure`, `icons_or_complex_assets`, `dense_or_repeated_content`,
and `footer_or_edge_system`.

For every region record observable reference features, observable candidate
features, and remaining material mismatches. Do not write generic claims such
as “aligned” or “preserved” without those observations. A region can pass only
when its mismatch list is empty and it is linked to a same-coordinate crop in
the final local-crop report.

Run:

```bash
python3 scripts/validate_visual_closeout.py \
  --closeout PROJECT/visual-closeout.json \
  --local-crop-report PROJECT/local-crop-visual.json \
  --text-render-feedback PROJECT/text-render-feedback.json \
  --report PROJECT/visual-closeout-validation.json
```

Every `repair_required=true` text-render record must either disappear after a
fresh feedback run or have an object-specific disposition with status
`resolved` or `false_positive_verified`, an after-render path, and a concrete
review note. PASS is forbidden while a material mismatch or text-render repair
remains open. The reference, local-crop report, text feedback and closeout must
all bind the same final hashes.
