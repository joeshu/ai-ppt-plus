#!/usr/bin/env python3
"""Extract independent panel assets from a full-resolution frame image."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr); raise SystemExit(2)

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source")
    ap.add_argument("manifest", help="JSON containing panels[].panel_id and source_bbox:[x,y,w,h].")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--out-manifest", required=True)
    args = ap.parse_args()
    src, mp = Path(args.source), Path(args.manifest)
    if not src.exists() or not mp.exists(): die("source and manifest must exist")
    try:
        from PIL import Image
    except ImportError: die("Pillow is required")
    data = json.loads(mp.read_text(encoding="utf-8"))
    if data.get("status") != "approved":
        die("panel manifest must have status=approved; pass candidates through approve_panel_candidates.py first")
    approval = data.get("approval")
    if not isinstance(approval, dict) or not approval.get("reviewer") or not approval.get("revision"):
        die("approved panel manifest must include approval.reviewer and approval.revision")
    declared_source = data.get("source_sha256")
    if declared_source and sha256(src) != declared_source:
        die("source image SHA-256 does not match the approved candidate manifest")
    panels = data.get("panels")
    if not isinstance(panels, list) or not panels: die("manifest must contain non-empty panels[]")
    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True); emitted = []
    with Image.open(src) as im:
        rgba = im.convert("RGBA"); sw, sh = rgba.size
        for i, panel in enumerate(panels, 1):
            pid = str(panel.get("panel_id") or f"panel-{i:02d}")
            bbox = panel.get("source_bbox")
            if not isinstance(bbox, list) or len(bbox) != 4: die(f"{pid}: source_bbox must be [x,y,w,h]")
            x, y, w, h = [int(round(float(v))) for v in bbox]
            if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > sw or y + h > sh:
                die(f"{pid}: bbox outside source {sw}x{sh}: {bbox}")
            name = Path(str(panel.get("file") or f"{pid}.png")).name
            rgba.crop((x, y, x + w, y + h)).save(out_dir / name)
            emitted.append({**panel, "panel_id": pid, "file": name,
                            "source_bbox": [x, y, w, h], "asset_size": [w, h],
                            "formal_text_baked_in": bool(panel.get("formal_text_baked_in", False))})
    result = {"schema":"ai-ppt-plus/panel-assets/v1", "status":"approved", "source":str(src), "source_size":[sw, sh], "source_sha256":sha256(src), "whole_frame":False, "approval":approval, "panels":emitted}
    out = Path(args.out_manifest); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid":True, "panel_count":len(emitted), "manifest":str(out)}, ensure_ascii=False))

if __name__ == "__main__": main()
