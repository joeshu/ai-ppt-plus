"""Real LibreOffice/PDF measurements for isolated typography calibration.

PDF text bounds measure layout, not exact ink silhouettes. The caller must use
the same metric for the target. Final page QA still detects occlusion and art.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
import tempfile


def measure_text(deck, object_id, *, timeout=60):
    import fitz
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from authoring_backend import build_pptx
    matches = [(slide, text) for slide in deck["slides"] for text in slide.get("texts", [])
               if object_id in (text.get("id"), text.get("object_id"), text.get("name"))]
    if len(matches) != 1:
        raise ValueError("exactly one native text object required")
    _, text = matches[0]
    if deck.get("units", "fraction") != "fraction":
        raise ValueError("measurement requires normalized coordinates")
    trial = deepcopy(deck)
    # Same writer, canvas and text geometry; isolate to avoid neighboring copy.
    trial["slides"] = [{"texts": [deepcopy(text)]}]
    family = text.get("font") or deck.get("theme", {}).get("font")
    expected = "".join(r["text"] for r in text.get("runs", [])) if text.get("runs") else text.get("text", "")
    with tempfile.TemporaryDirectory(prefix="ppt-typography-") as folder:
        root = Path(folder)
        pptx = root / "trial.pptx"
        build_pptx(trial, pptx)
        subprocess.run(["soffice", f"-env:UserInstallation={(root / 'profile').as_uri()}",
                        "--headless", "--convert-to", "pdf", "--outdir", str(root), str(pptx)],
                       capture_output=True, check=True, timeout=timeout)
        pdf = root / "trial.pdf"
        with fitz.open(pdf) as document:
            page = document[0]
            lines = [line for block in page.get_text("dict")["blocks"] if "lines" in block
                     for line in block["lines"] if line.get("spans")]
            if not lines:
                raise ValueError("renderer produced no text")
            spans = [span for line in lines for span in line["spans"]]
            bounds = [min(s["bbox"][0] for s in spans), min(s["bbox"][1] for s in spans),
                      max(s["bbox"][2] for s in spans), max(s["bbox"][3] for s in spans)]
            width, height = page.rect.width, page.rect.height
            x, y, right, bottom = bounds
            # Exact text readback ignores only whitespace introduced by wrapping.
            readback = "".join(s["text"] for s in spans)
            copy_valid = "".join(readback.split()) == "".join(expected.split())
            norm = lambda s: "".join(c.lower() for c in s if c.isalnum())
            families = {norm(text.get("font") or family or "")}
            families.update(norm(r.get("font") or family or "") for r in text.get("runs", []))
            font_verified = bool(family) and all(any(f and f in norm(s["font"]) for f in families) for s in spans)
            tx, ty, tw, th = (float(text[k]) for k in ("x", "y", "w", "h"))
            overflow = (not copy_valid or x / width < tx - .002 or y / height < ty - .002
                        or right / width > tx + tw + .002 or bottom / height > ty + th + .002)
            return {"renderer": "LibreOffice/PDF", "measurement_kind": "pdf-text-bounds",
                    "render_sha256": sha256(pdf.read_bytes()).hexdigest(),
                    "deck_sha256": sha256(pptx.read_bytes()).hexdigest(),
                    "font_verified": font_verified, "overflow": overflow,
                    "copy_valid": copy_valid, "line_count": len(lines),
                    "ink_bbox": [x / width, y / height, (right - x) / width, (bottom - y) / height],
                    "baselines": [line["spans"][0]["origin"][1] / height for line in lines]}
