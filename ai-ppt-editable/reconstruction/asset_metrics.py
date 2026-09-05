"""Local asset evidence covering silhouette, colour and internal structure."""
from hashlib import sha256
from pathlib import Path
import numpy as np
from PIL import Image


def compare_asset_subjects(reference, candidate, *, size=256, alpha_threshold=8):
    if not isinstance(size, int) or not 16 <= size <= 1024:
        raise ValueError("invalid comparison size")
    if not isinstance(alpha_threshold, int) or not 1 <= alpha_threshold <= 255:
        raise ValueError("invalid alpha threshold")
    def sample(path):
        data = Path(path).read_bytes()
        from io import BytesIO
        with Image.open(BytesIO(data)) as im:
            if "A" not in im.getbands():
                raise ValueError("approved alpha reference/candidate required")
            rgba = im.convert("RGBA")
            alpha = rgba.getchannel("A").point(lambda p: 255 if p >= alpha_threshold else 0)
            box = alpha.getbbox()
            if box is None:
                raise ValueError("empty asset")
            cropped_alpha = alpha.crop(box)
            cropped_rgba = rgba.crop(box)
            cropped_rgba.thumbnail((size, size), Image.Resampling.LANCZOS)
            cropped_alpha.thumbnail((size, size), Image.Resampling.NEAREST)
            rgba_canvas = Image.new("RGBA", (size, size))
            alpha_canvas = Image.new("L", (size, size))
            offset = ((size - cropped_rgba.width) // 2, (size - cropped_rgba.height) // 2)
            rgba_canvas.paste(cropped_rgba, offset, cropped_rgba)
            alpha_canvas.paste(cropped_alpha, offset)
            return np.asarray(alpha_canvas) > 0, np.asarray(rgba_canvas, dtype=np.float32), sha256(data).hexdigest()
    ref, ref_rgba, ref_hash = sample(reference)
    actual, actual_rgba, actual_hash = sample(candidate)
    intersection = np.logical_and(ref, actual).sum()
    union = np.logical_or(ref, actual).sum()
    common = np.logical_and(ref, actual)
    if common.any():
        colour_mae = float(np.abs(ref_rgba[common, :3] - actual_rgba[common, :3]).mean() / 255)
        colour_similarity = 1.0 - colour_mae
        ref_luma = ref_rgba[..., :3].mean(axis=2)
        actual_luma = actual_rgba[..., :3].mean(axis=2)
        internal_similarity = 1.0 - float(np.abs(ref_luma[common] - actual_luma[common]).mean() / 255)
    else:
        colour_similarity = internal_similarity = 0.0
    return {"silhouette_iou": float(intersection / union),
            "colour_similarity": colour_similarity,
            "internal_structure_similarity": internal_similarity,
            "reference_sha256": ref_hash, "candidate_sha256": actual_hash,
            "scope": "silhouette-colour-internal-structure", "alpha_threshold": alpha_threshold,
            "semantic_style_review_required": True}
