from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from reconstruction.asset_orchestrator import validate_generated_asset


def _json_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _placement_from_result(result, slot: tuple[int, int, int, int], request: Mapping[str, Any]) -> tuple[int, int, int, int]:
    """Apply the same contained visible-alpha centroid fit as PPTX placement."""
    x, y, width, height = slot
    if request.get("align_visible_alpha") is not True:
        return slot
    left, top, right, bottom = (float(v) for v in result.visible_alpha_bbox)
    visible_x = left * result.width
    visible_y = top * result.height
    visible_w = max(1e-9, (right - left) * result.width)
    visible_h = max(1e-9, (bottom - top) * result.height)
    contain = max(0.05, min(1.0, float(request.get("visible_contain", 1.0))))
    fit_w, fit_h = width * contain, height * contain
    scale = min(fit_w / visible_w, fit_h / visible_h)
    centroid_x = float(result.alpha_centroid[0]) * result.width
    centroid_y = float(result.alpha_centroid[1]) * result.height
    target_cx, target_cy = x + width / 2.0, y + height / 2.0
    placed_x = target_cx - centroid_x * scale
    placed_y = target_cy - centroid_y * scale
    safe_left = x + (width - fit_w) / 2.0
    safe_top = y + (height - fit_h) / 2.0
    safe_right = safe_left + fit_w
    safe_bottom = safe_top + fit_h
    visible_left = placed_x + visible_x * scale
    visible_top = placed_y + visible_y * scale
    visible_right = visible_left + visible_w * scale
    visible_bottom = visible_top + visible_h * scale
    if visible_left < safe_left:
        placed_x += safe_left - visible_left
    elif visible_right > safe_right:
        placed_x -= visible_right - safe_right
    if visible_top < safe_top:
        placed_y += safe_top - visible_top
    elif visible_bottom > safe_bottom:
        placed_y -= visible_bottom - safe_bottom
    return (
        int(round(placed_x)),
        int(round(placed_y)),
        max(1, int(round(result.width * scale))),
        max(1, int(round(result.height * scale))),
    )


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
        placement = _placement_from_result(result, slot, request)
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
            "placement_transform": "alpha-centroid-fit-contained" if request.get("align_visible_alpha") is True else "slot-bbox",
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
        if approved:
            delivered = self.job_dir / "delivered.png"
            shutil.copy2(record["asset"]["file"], delivered)
            state.update({"status": "passed", "delivered": str(delivered), "asset_sha256": hashlib.sha256(delivered.read_bytes()).hexdigest(), "local_crop_qa": str(review_path)})
        else:
            state.update({"status": "retry_required", "local_crop_qa": str(review_path), "retry_scope": "asset_only"})
        self._write(self.state_path, state)
        return state
