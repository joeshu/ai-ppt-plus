from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from reconstruction.asset_orchestrator import bind_generated_asset, validate_generated_asset


def _json_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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
        validation = validate_generated_asset(request, {"object_id": self.job["asset_id"], "file": str(staged), "background_mode": request.get("background_mode", "transparent")})
        if not validation.valid:
            raise ValueError("generated asset failed byte/alpha validation: " + "; ".join(validation.issues))
        sw, sh = self.slide_size_emu
        geom = request.get("preserve_geometry", {})
        slot = (int(float(geom.get("x", 0)) * sw), int(float(geom.get("y", 0)) * sh), int(float(geom.get("w", 0)) * sw), int(float(geom.get("h", 0)) * sh))
        bound = bind_generated_asset(str(staged), slot)
        record = {
            "asset_id": self.job["asset_id"],
            "attempt": attempt,
            "asset": {"file": str(staged), "sha256": hashlib.sha256(staged.read_bytes()).hexdigest()},
            "validation": asdict(validation),
            "alpha_geometry": bound.alpha_geometry,
            "placement_bbox_emu": list(bound.placement_bbox),
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
