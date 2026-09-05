"""Place transparent assets by visible subject, retaining the complete PNG."""
from hashlib import sha256
from math import isfinite
from PIL import Image


def subject_placement(path, target_bbox, *, alpha_threshold=8, aspect_tolerance=.03):
    """Fit full-image geometry so alpha subject matches the requested region.

    Does not crop, redraw, regenerate or alter image bytes. Visual style QA is
    still mandatory; alpha geometry is not evidence of silhouette similarity.
    """
    if not 1 <= alpha_threshold <= 255 or not isfinite(aspect_tolerance) or aspect_tolerance < 0:
        raise ValueError("invalid alpha/aspect threshold")
    x, y, w, h = map(float, target_bbox)
    if not all(isfinite(v) for v in (x, y, w, h)) or w <= 0 or h <= 0:
        raise ValueError("invalid target bbox")
    with Image.open(path) as original:
        if "A" not in original.getbands():
            raise ValueError("explicit alpha channel required")
        alpha = original.getchannel("A")
        bbox = alpha.point(lambda value: 255 if value >= alpha_threshold else 0).getbbox()
        if bbox is None:
            raise ValueError("empty asset")
        iw, ih = original.size
    left, top, right, bottom = bbox
    sw, sh = right - left, bottom - top
    # Target coordinates must share an isotropic unit (pixels or inches).
    if abs((w / h) / (sw / sh) - 1) > aspect_tolerance:
        raise ValueError("subject aspect mismatch; do not stretch asset")
    scale = min(w / sw, h / sh)
    px = x + (w - sw * scale) / 2 - left * scale
    py = y + (h - sh * scale) / 2 - top * scale
    from pathlib import Path
    return {"image_bbox": [px, py, iw * scale, ih * scale],
            "subject_bbox_px": list(bbox), "asset_sha256": sha256(Path(path).read_bytes()).hexdigest(),
            "alpha_threshold": alpha_threshold}
