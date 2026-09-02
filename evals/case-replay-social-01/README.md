# Social-channel commission anchor replay

This package is the persisted replay evidence for
`social-channel-commission-native-01`.

```bash
python scripts/replay_pptx_case.py --phase baseline ...
python scripts/replay_pptx_case.py --phase candidate ...
python scripts/validate_distillation_improvement.py --mode replay ...
```

The exact uploaded source deck and green-screen process image are retained in
`source/`; the optimized editable deck is retained in `optimized-pptx/`.
Their SHA-256 values are recorded here so a future replay cannot silently use
a different input:

- source deck: `3337f2a88468174b135b411d9a93af822f4f47370589eb2d0a9d9df3070997fb`
- process image: `0cdaa9687302d076d063c0b48a6bf18c0fff5156c7cdc8afef4573efc0327d75`
- optimized deck: `a0282fe9db8a23e216bdc68b10d6cf92b5ed5759c211787478079a2ce4108372`

The reports bind their hashes and record the original green-screen process
image, rendered comparison, five native `a:tbl` tables, four vertical merges,
native panels/text, and mutation smoke evidence. `case-improvement.json` is a
technical improvement proof only; final case-library admission still requires
human visual review.
