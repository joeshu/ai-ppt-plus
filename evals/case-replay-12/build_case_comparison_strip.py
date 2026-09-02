#!/usr/bin/env python3
"""Build a compact reference-vs-editable review strip for the case package."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
THUMBNAIL = (640, 360)
CARD = (THUMBNAIL[0] * 2 + 36, THUMBNAIL[1] + 64)


def font(size: int):
    candidates = [
        ROOT.parents[1] / "ai-ppt-editable/assets/fonts/NotoSansSC-Regular.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def fit(path: Path) -> Image.Image:
    with Image.open(path).convert("RGB") as image:
        image.thumbnail(THUMBNAIL, Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", THUMBNAIL, "#061A35")
        left = (THUMBNAIL[0] - image.width) // 2
        top = (THUMBNAIL[1] - image.height) // 2
        canvas.paste(image, (left, top))
        return canvas


def main() -> int:
    cases = json.loads((ROOT / "case-suite.json").read_text(encoding="utf-8"))["cases"]
    output = ROOT / "qa" / "reference-vs-candidate"
    output.mkdir(parents=True, exist_ok=True)
    small_font = font(20)
    label_font = font(18)
    cards = []
    for case in cases:
        case_id = case["case_id"]
        reference = ROOT / "visual" / f"{case_id}-reference.png"
        candidate = ROOT / "runs" / "candidate" / case_id / "render" / "slide-1.png"
        if not reference.is_file() or not candidate.is_file():
            raise FileNotFoundError(f"missing comparison image for {case_id}")
        card = Image.new("RGB", CARD, "#0A2544")
        draw = ImageDraw.Draw(card)
        draw.text((12, 8), case_id, fill="#F4F7FB", font=label_font)
        draw.text((12, 34), "REFERENCE", fill="#E60012", font=small_font)
        draw.text((CARD[0] // 2 + 18, 34), "EDITABLE CANDIDATE", fill="#1687FF", font=small_font)
        card.paste(fit(reference), (12, 56))
        card.paste(fit(candidate), (CARD[0] // 2 + 18, 56))
        card_path = output / f"{case_id}.png"
        card.save(card_path, optimize=True)
        cards.append(card)
    strip = Image.new("RGB", (CARD[0] * 2, CARD[1] * ((len(cards) + 1) // 2)), "#061A35")
    for index, card in enumerate(cards):
        strip.paste(card, ((index % 2) * CARD[0], (index // 2) * CARD[1]))
    strip.save(ROOT / "qa" / "reference-vs-candidate-strip.png", optimize=True)
    print(json.dumps({"cases": len(cards), "strip": "qa/reference-vs-candidate-strip.png", "directory": "qa/reference-vs-candidate"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
