"""Local alpha silhouette evidence; does not replace semantic/style review."""
from hashlib import sha256
from pathlib import Path
import numpy as np
from PIL import Image


def compare_asset_subjects(reference, candidate, *, size=256, alpha_threshold=8):
    if not isinstance(size, int) or not 16 <= size <= 1024:
        raise ValueError("invalid comparison size")
    if not isinstance(alpha_threshold, int) or not 1 <= alpha_threshold <= 255:
        raise ValueError("invalid alpha threshold")
    def mask(path):
        data = Path(path).read_bytes()
        from io import BytesIO
        with Image.open(BytesIO(data)) as im:
            if "A" not in im.getbands():
                raise ValueError("approved alpha reference/candidate required")
            alpha = im.getchannel("A").point(lambda p: 255 if p >= alpha_threshold else 0)
            box = alpha.getbbox()
            if box is None:
                raise ValueError("empty asset")
            cropped = alpha.crop(box)
            cropped.thumbnail((size, size), Image.Resampling.NEAREST)
            canvas = Image.new("L", (size, size))
            canvas.paste(cropped, ((size - cropped.width) // 2, (size - cropped.height) // 2))
            return np.asarray(canvas) > 0, sha256(data).hexdigest()
    ref, ref_hash = mask(reference)
    actual, actual_hash = mask(candidate)
    intersection = np.logical_and(ref, actual).sum()
    union = np.logical_or(ref, actual).sum()
    return {"silhouette_iou": float(intersection / union),
            "reference_sha256": ref_hash, "candidate_sha256": actual_hash,
            "scope": "alpha-silhouette-only", "alpha_threshold": alpha_threshold,
            "semantic_style_review_required": True}
