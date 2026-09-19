# Runtime font portability and CJK OOXML contract

## Principle

Fonts are an **environment capability**, not a large binary asset of the skill
repository. Keep font policy, resolution logic, provenance and OOXML binding in
Git; keep TTF/TTC/OTF files in the operating system, user project, or ignored
runtime cache.

This follows the useful Knight reconstruction pattern: use a real font for text
measurement, bind the East Asian typeface in PowerPoint OOXML, render the PPTX,
and inspect the result. Do not make repository size the mechanism for font
correctness.

## Runtime resolution

For Chinese work:

1. honor an explicitly supplied licensed project font;
2. otherwise resolve the declared family from the host (`fontconfig` on Linux,
   installed system fonts on Windows/macOS);
3. prefer `Noto Sans CJK SC` for deterministic Linux CI; Microsoft YaHei,
   PingFang SC, HarmonyOS Sans SC and other declared families are valid only
   when actually installed and resolved;
4. fail closed when no CJK-capable face can be resolved. Never silently switch
   to an unknown serif/default font.

Use `scripts/runtime_fonts.py` to inspect the environment. When a tool needs
file paths rather than a family name, materialize an ignored task-local cache:

```bash
python scripts/prepare_runtime_fonts.py \
  --family "Noto Sans CJK SC" \
  --output-dir .runtime/fonts \
  --report .runtime/font-runtime.json
```

The cache is generated from installed fonts and must not be committed.

## Measurement and authoring parity

Text-fit measurement and PPTX authoring must use the same resolved family/face.
Record the resolved file path and SHA-256 in runtime evidence. A font-family
string alone is not render proof.

For every PowerPoint text run, set the normal run family and explicit CJK
OOXML typefaces. The native writer must keep `run.font.name` plus `a:ea` and
`a:cs` typeface declarations aligned to the same family. This reduces
PowerPoint/LibreOffice fallback drift while preserving native editable text.

## CI

CI installs the open-source Noto CJK package through the operating system,
refreshes fontconfig, materializes the ignored runtime cache, then runs package,
text-fit, authoring and render regression tests. The repository therefore does
not need duplicated 40+ MB CJK font binaries.

## Hard gates

- unresolved CJK family: blocker;
- silent font substitution: blocker;
- blank/missing Chinese glyphs in fresh render: blocker;
- text-fit measured with a different face than authoring: blocker;
- missing `a:ea` on CJK runs: blocker;
- repository font binary reintroduced under `assets/fonts`: repository-hygiene blocker.

Font embedding remains an explicit compatibility option, not a requirement for
normal strict Artifact Tool authoring. If embedding is requested, use a
licensed task-local font and verify the embedded OOXML parts separately.
