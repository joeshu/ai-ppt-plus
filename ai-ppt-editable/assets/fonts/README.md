# Portable CJK font fallback

The `NotoSansSC-*.ttf` files are the portable Chinese fallback used for local
rendering and font parity checks when a user-provided font is unavailable.

The task-local set contains real static 400/500/600/700 faces:

- `NotoSansSC-Regular.ttf` — 400
- `NotoSansSC-Medium.ttf` — 500
- `NotoSansSC-SemiBold.ttf` — 600
- `NotoSansSC-Bold.ttf` — 700

- Family: Noto Sans CJK SC
- License: SIL Open Font License 1.1
- Source: Noto CJK / validated reconstruction asset
- Source file: `NotoSansSC-VF.ttf`
- Source SHA-256: `763146584cf0710223441356b4395e279021b0806c196614377a7a0174ae074a`
- Generation: `fontTools.varLib.instancer` static `wght` instances
- License text: https://scripts.sil.org/OFL
- SHA-256: `2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b`
- Additional face hashes are recorded in `font-manifest.json`.

Microsoft YaHei remains preferred when it is supplied by the user or already
available on the target device. Do not copy or redistribute Microsoft fonts.
