# Runtime-managed CJK fonts

This directory intentionally contains **policy and license metadata only**. Large
TTF/TTC binaries are not repository assets.

For Chinese authoring, resolve a real installed CJK family from the runtime
environment. The preferred CI/runtime family is `Noto Sans CJK SC`; platform
fonts such as Microsoft YaHei or PingFang SC may be used when they are actually
installed and selected by the deck.

Run:

```bash
python scripts/prepare_runtime_fonts.py \
  --family "Noto Sans CJK SC" \
  --output-dir .runtime/fonts \
  --report .runtime/font-runtime.json
```

The generated `.runtime/fonts` cache is ignored by Git. Text fitting and strict
authoring must use the same resolved face. If no CJK-capable face can be
resolved, fail closed rather than silently substituting an unknown font.

PowerPoint text runs must also bind the declared family in OOXML, including the
East Asian typeface (`a:ea`) and complex-script typeface (`a:cs`) in addition
to the normal run family. This reduces viewer-specific CJK fallback and layout
drift without committing font binaries to the skill repository.
