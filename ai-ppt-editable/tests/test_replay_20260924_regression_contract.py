#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    regressions = (ROOT / "references" / "image-to-editable-regressions.md").read_text(encoding="utf-8")
    dense = (ROOT / "references" / "dense-single-slide-reconstruction.md").read_text(encoding="utf-8")
    assert "VIS-ASSET-PATH-NOT-EMBEDDED" in regressions
    assert "VIS-CHART-LABEL-WRAP" in regressions
    assert "decoded image bytes plus content type" in regressions
    assert "automatic data" in dense and "labels and author stable" in dense
    assert "narrow painted center must not use `contain`" in dense
    print("2026-09-24 replay regression contract: ok")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
