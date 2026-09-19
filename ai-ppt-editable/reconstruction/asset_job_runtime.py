from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from reconstruction.asset_orchestrator import validate_generated_asset


def _json_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _bbox_iou(a, b) -> float:
    ax, ay, aw, ah = (float(v) for v in a)
    bx, by, bw, bh = (float(v) for v in b)
    ix0, iy0 = max(ax, bx), max(ay, by)
    ix1, iy1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    union = aw * ah + bw * bh - inter
    return 0.0 if union <= 0 else inter / union


def _placement_geometry_qa(reference_bbox, candidate_bbox, *, min_iou=0.90, max_centroid_error=0.03, max_scale_error=0.05) -> dict[str, Any]:
    """Classify pure placement drift separately from generated-content defects."""
    ref = [float(v) for v in reference_bbox]
    cand = [float(v) for v in candidate_bbox]
    rx, ry, rw, rh = ref
    cx, cy, cw, ch = cand
    if rw <= 0 or rh <= 0 or cw <= 0 or ch <= 0:
        raise ValueError("placement geometry bbox must have positive size")
    centroid_error = math.hypot((cx + cw / 2) - (rx + rw / 2), (cy + ch / 2) - (ry + rh / 2))
    scale_error = max(abs(cw / rw - 1.0), abs(ch / rh - 1.0))
    iou = _bbox_iou(ref, cand)
    issues = []
    if iou < min_iou:
        issues.append("local_crop_bbox_iou_low")
    if centroid_error > max_centroid_error:
        issues.append("local_crop_centroid_drift")
    if scale_error > max_scale_error:
        issues.append("local_crop_scale_drift")
    return {
        "schema": "ai-ppt-plus/local-crop-geometry-qa/v1",
        "approved": not issues,
        "reference_visible_bbox_norm": ref,
        "candidate_visible_bbox_norm": cand,
        "visible_bbox_iou": iou,
        "centroid_error_norm": centroid_error,
        "scale_error": scale_error,
        "issue_codes": issues,
        "repair_scope": "none" if not issues else "placement_only",
        "thresholds": {
            "min_iou": min_iou,
            "max_centroid_error": max_centroid_error,
            "max_scale_error": max_scale_error,
        },
    }


def _placement_from_result(result, slot: tuple[int, int, int, int], request: Mapping[str, Any]) -> tuple[tuple[int, int, int, int], dict[str, Any]]:
    """Choose deterministic placement and return transform evidence."""
    x, y, width, height = slot
    if request.get("align_visible_alpha") is not True:
        return slot, {"mode": "slot-bbox"}

    left, top, right, bottom = (float(v) for v in result.visible_alpha_bbox)
    visible_x, visible_y = left * result.width, top * result.height
    visible_w = max(1e-9, (right - left) * result.width)
    visible_h = max(1e-9, (bottom - top) * result.height)
    centroid_x = float(result.alpha_centroid[0]) * result.width
    centroid_y = float(result.alpha_centroid[1]) * result.height

    reference_bbox = request.get("reference_visible_bbox_norm")
    if reference_bbox is not None:
        if not isinstance(reference_bbox, (list, tuple)) or len(reference_bbox) != 4:
            raise ValueError("reference_visible_bbox_norm must contain four values")
        rx, ry, rw, rh = (float(v) for v in reference_bbox)
        if rw <= 0 or rh <= 0 or rx < 0 or ry < 0 or rx + rw > 1 or ry + rh > 1:
            raise ValueError("invalid reference_visible_bbox_norm")
        target_x, target_y = x + rx * width, y + ry * height
        target_w, target_h = rw * width, rh * height
        scale = min(target_w / visible_w, target_h / visible_h)
        visible_out_w, visible_out_h = visible_w * scale, visible_h * scale
        placed_x = target_x + (target_w - visible_out_w) / 2.0 - visible_x * scale
        placed_y = target_y + (target_h - visible_out_h) / 2.0 - visible_y * scale
        placement = (
            int(round(placed_x)), int(round(placed_y)),
            max(1, int(round(result.width * scale))),
            max(1, int(round(result.height * scale))),
        )
        return placement, {"mode": "reference-visible-fit", "reference_visible_bbox_norm": list(reference_bbox)}

    pads = [left, top, 1.0 - right, 1.0 - bottom]
    pad_tol = float(request.get("padding_balance_tolerance", 0.14))
    centroid_tol = float(request.get("centroid_tolerance", 0.10))
    aspect_tol = float(request.get("aspect_ratio_tolerance", 0.15))
    min_extent = float(request.get("min_visible_extent", 0.42))
    balanced = abs(pads[0] - pads[2]) <= pad_tol and abs(pads[1] - pads[3]) <= pad_tol
    centered = abs(float(result.alpha_centroid[0]) - 0.5) <= centroid_tol and abs(float(result.alpha_centroid[1]) - 0.5) <= centroid_tol
    canvas_ar = result.width / result.height
    slot_ar = width / height
    aspect_match = abs(math.log(max(1e-9, canvas_ar / slot_ar))) <= aspect_tol
    visible_extent_ok = (right - left) >= min_extent and (bottom - top) >= min_extent
    if str(request.get("placement_mode") or "") == "adaptive-alpha-fit" and balanced and centered and aspect_match and visible_extent_ok:
        return slot, {
            "mode": "canvas-slot-fit",
            "padding_norm": pads,
            "balanced_padding": True,
            "centroid_centered": True,
            "aspect_match": True,
            "visible_extent_ok": True,
        }

    contain = max(0.05, min(1.0, float(request.get("visible_contain", 1.0))))
    fit_w, fit_h = width * contain, height * contain
    scale = min(fit_w / visible_w, fit_h / visible_h)
    target_cx, target_cy = x + width / 2.0, y + height / 2.0
    placed_x, placed_y = target_cx - centroid_x * scale, target_cy - centroid_y * scale
    safe_left = x + (width - fit_w) / 2.0
    safe_top = y + (height - fit_h) / 2.0
    safe_right, safe_bottom = safe_left + fit_w, safe_top + fit_h
    visible_left, visible_top = placed_x + visible_x * scale, placed_y + visible_y * scale
    visible_right, visible_bottom = visible_left + visible_w * scale, visible_top + visible_h * scale
    if visible_left < safe_left:
        placed_x += safe_left - visible_left
    elif visible_right > safe_right:
        placed_x -= visible_right - safe_right
    if visible_top < safe_top:
        placed_y += safe_top - visible_top
    elif visible_bottom > safe_bottom:
        placed_y -= visible_bottom - safe_bottom
    placement = (
        int(round(placed_x)), int(round(placed_y)),
        max(1, int(round(result.width * scale))),
        max(1, int(round(result.height * scale))),
    )
    return placement, {
        "mode": "alpha-centroid-fit-contained",
        "padding_norm": pads,
        "balanced_padding": balanced,
        "centroid_centered": centered,
        "aspect_match": aspect_match,
        "visible_extent_ok": visible_extent_ok,
    }


def _candidate_visible_bbox_norm(result, slot, placement) -> list[float]:
    x, y, width, height = slot
    px, py, pw, ph = placement
    left, top, right, bottom = (float(v) for v in result.visible_alpha_bbox)
    visible_x = px + left * pw
    visible_y = py + top * ph
    visible_w = (right - left) * pw
    visible_h = (bottom - top) * ph
    return [(visible_x - x) / width, (visible_y - y) / height, visible_w / width, visible_h / height]


class AssetJobRuntime:
    """Deterministic runtime for one ImageGen asset job.

    The runtime is deliberately asset-scoped: cache lookup, byte validation,
    alpha geometry, local-crop review and retry evidence are persisted per job.
    It never falls back to a source crop automatically.
    """

    def __init__(self, job: Mapping[str, Any], run_root: str | Path, source_image: str | Path, *, slide_size_emu: tuple[int, int], render_context: str = "default") -> None:
        self.job = dict(job)
        self.run_root = Path(run_root)
        self.source_image = Path(source_image)
        self.slide_size_emu = tuple(int(x) for x in slide_size_emu)
        self.render_context = str(render_context)
        basis = {"cache_key": self.job.get("cache_key"), "render_context": self.render_context, "slide_size_emu": self.slide_size_emu}
        self.runtime_key = _json_hash(basis)
        self.job_dir = self.run_root / "asset-jobs" / str(self.job["asset_id"]) / self.runtime_key
        self.state_path = self.job_dir / "state.json"
        self.job_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def load_state(self) -> dict[str, Any]:
        if self.state_path.exists():
            return self._read(self.state_path)
        return {"asset_id": self.job["asset_id"], "runtime_key": self.runtime_key, "attempts": [], "status": "planned"}

    def cache_hit(self) -> dict[str, Any] | None:
        state = self.load_state()
        if state.get("status") != "passed":
            return None
        delivered = state.get("delivered")
        if not delivered:
            return None
        p = Path(delivered)
        if not p.exists():
            return None
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        if sha != state.get("asset_sha256"):
            return None
        return state

    def register(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        attempt = int(receipt.get("attempt", 1))
        attempt_dir = self.job_dir / f"attempt-{attempt}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        generated = Path(str(receipt["generated_source"]))
        if not generated.exists():
            raise FileNotFoundError(generated)
        staged = attempt_dir / "generated.png"
        shutil.copy2(generated, staged)
        request = dict(self.job.get("request", {}))
        # Validation is fail-closed: validate_generated_asset returns a
        # GeneratedAssetResult on success and raises AssetGenerationError on
        # any byte/background/alpha/provenance contract violation.
        result = validate_generated_asset(
            request,
            {
                "object_id": self.job["asset_id"],
                "file": str(staged),
                "background_mode": request.get("background_mode", "transparent"),
            },
        )
        sw, sh = self.slide_size_emu
        geom = request.get("preserve_geometry", {})
        slot = (
            int(float(geom.get("x", 0)) * sw),
            int(float(geom.get("y", 0)) * sh),
            int(float(geom.get("w", 0)) * sw),
            int(float(geom.get("h", 0)) * sh),
        )
        placement, placement_evidence = _placement_from_result(result, slot, request)
        candidate_visible_bbox_norm = _candidate_visible_bbox_norm(result, slot, placement)
        reference_bbox = request.get("reference_visible_bbox_norm")
        placement_qa = _placement_geometry_qa(reference_bbox, candidate_visible_bbox_norm) if reference_bbox is not None else None
        record = {
            "asset_id": self.job["asset_id"],
            "attempt": attempt,
            "asset": {"file": str(staged), "sha256": result.sha256},
            "validation": asdict(result),
            "alpha_geometry": {
                "canvas_px": [result.width, result.height],
                "visible_alpha_bbox": list(result.visible_alpha_bbox),
                "alpha_centroid": list(result.alpha_centroid),
            },
            "intended_slot_bbox_emu": list(slot),
            "placement_bbox_emu": list(placement),
            "placement_transform": placement_evidence["mode"],
            "placement_evidence": placement_evidence,
            "candidate_visible_bbox_norm": candidate_visible_bbox_norm,
            "placement_geometry_qa": placement_qa,
            "receipt": dict(receipt),
        }
        registered = attempt_dir / "registered.json"
        self._write(registered, record)
        state = self.load_state()
        state["status"] = "registered"
        state["registered"] = str(registered)
        state.setdefault("attempts", []).append({"attempt": attempt, "registered": str(registered)})
        self._write(self.state_path, state)
        return state

    def review(self, evidence: Mapping[str, Any]) -> dict[str, Any]:
        state = self.load_state()
        registered = Path(str(state.get("registered", "")))
        if not registered.exists():
            raise RuntimeError("review requires a registered asset")
        record = self._read(registered)
        approved = bool(evidence.get("review", evidence).get("approved", False))
        review_path = registered.parent / "local-crop-qa.json"
        self._write(review_path, dict(evidence))
        placement_qa = record.get("placement_geometry_qa")
        if placement_qa and not placement_qa.get("approved", False):
            state.update({
                "status": "placement_repair_required",
                "local_crop_qa": str(review_path),
                "retry_scope": "placement_only",
                "placement_issue_codes": placement_qa.get("issue_codes", []),
            })
        elif approved:
            delivered = self.job_dir / "delivered.png"
            shutil.copy2(record["asset"]["file"], delivered)
            state.update({"status": "passed", "delivered": str(delivered), "asset_sha256": hashlib.sha256(delivered.read_bytes()).hexdigest(), "local_crop_qa": str(review_path)})
        else:
            state.update({"status": "retry_required", "local_crop_qa": str(review_path), "retry_scope": "asset_only"})
        self._write(self.state_path, state)
        return state
