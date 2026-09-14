# Font preflight contract

Font discovery is evidence, not a declaration. Before a full deck build, the
font preflight must exercise a title, body text, mixed CJK/Latin/numeric text,
punctuation, bold weights and colored emphasis, then record the renderer family
used by the exported smoke artifact. The same family and file SHA list flows
through Artifact Tool, Skia/font registration, finalizer and QA.

Reports expose available weights, missing 500/600/700 faces, simulated-bold
usage, fallback status and `native_font_rendering_verified`. Missing CJK glyphs,
silent fallback or an unverified native render blocks formal construction.
"fontPolicy" alone never counts as render proof.

Normalize a probe report with:

```bash
python scripts/font_preflight.py --report qa/font-report.json \
  --output qa/font-preflight.json --require-cjk --require-native-render
```
