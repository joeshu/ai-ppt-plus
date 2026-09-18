import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from reconstruction.asset_job_runtime import AssetJobRuntime


class AssetJobRuntimeTest(unittest.TestCase):
    def _job(self, **request_overrides):
        request = {
            "object_id": "icon-a",
            "background_mode": "transparent",
            "preserve_geometry": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4},
        }
        request.update(request_overrides)
        return {"asset_id": "icon-a", "cache_key": "abc", "request": request}

    @staticmethod
    def _transparent_asset(path, *, size=(64, 64), box=(16, 16, 48, 48), color=(220, 0, 20, 255)):
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        left, top, right, bottom = box
        for x in range(left, right):
            for y in range(top, bottom):
                im.putpixel((x, y), color)
        im.save(path)

    def test_register_review_and_cache_hit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.png"
            generated = root / "generated.png"
            Image.new("RGB", (64, 64), "white").save(source)
            self._transparent_asset(generated)
            rt = AssetJobRuntime(self._job(), root, source, slide_size_emu=(1000, 500), render_context="test")
            state = rt.register({"attempt": 1, "generated_source": str(generated)})
            self.assertEqual(state["status"], "registered")
            state = rt.review({"review": {"approved": True, "score": 1.0}})
            self.assertEqual(state["status"], "passed")
            self.assertIsNotNone(rt.cache_hit())

    def test_reject_review_is_asset_only_retry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.png"
            generated = root / "generated.png"
            Image.new("RGB", (64, 64), "white").save(source)
            self._transparent_asset(generated, box=(32, 32, 33, 33), color=(0, 0, 255, 255))
            rt = AssetJobRuntime(self._job(), root, source, slide_size_emu=(1000, 500))
            rt.register({"attempt": 1, "generated_source": str(generated)})
            state = rt.review({"review": {"approved": False, "issue_codes": ["shape_mismatch"]}})
            self.assertEqual(state["status"], "retry_required")
            self.assertEqual(state["retry_scope"], "asset_only")
            self.assertIsNone(rt.cache_hit())

    def test_alpha_centroid_placement_is_persisted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.png"
            generated = root / "generated.png"
            Image.new("RGB", (100, 100), "white").save(source)
            self._transparent_asset(generated, size=(100, 100), box=(20, 10, 80, 60))
            rt = AssetJobRuntime(
                self._job(align_visible_alpha=True, visible_contain=1.0),
                root,
                source,
                slide_size_emu=(1000, 500),
            )
            state = rt.register({"attempt": 1, "generated_source": str(generated)})
            record = json.loads(Path(state["registered"]).read_text(encoding="utf-8"))
            self.assertEqual(record["intended_slot_bbox_emu"], [100, 100, 300, 200])
            self.assertEqual(record["placement_bbox_emu"], [50, 60, 400, 400])
            self.assertEqual(record["placement_transform"], "alpha-centroid-fit")
            self.assertEqual(record["alpha_geometry"]["visible_alpha_bbox"], [0.2, 0.1, 0.8, 0.6])
            self.assertEqual(record["alpha_geometry"]["alpha_centroid"], [0.5, 0.35])

    def test_cache_invalidates_when_delivered_bytes_change(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.png"
            generated = root / "generated.png"
            Image.new("RGB", (64, 64), "white").save(source)
            self._transparent_asset(generated)
            rt = AssetJobRuntime(self._job(), root, source, slide_size_emu=(1000, 500))
            rt.register({"attempt": 1, "generated_source": str(generated)})
            state = rt.review({"review": {"approved": True}})
            self.assertIsNotNone(rt.cache_hit())
            Path(state["delivered"]).write_bytes(b"tampered")
            self.assertIsNone(rt.cache_hit())

    def test_invalid_transparent_output_fails_closed_without_source_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.png"
            generated = root / "generated.png"
            Image.new("RGB", (64, 64), "white").save(source)
            Image.new("RGBA", (64, 64), (255, 255, 255, 255)).save(generated)
            rt = AssetJobRuntime(self._job(), root, source, slide_size_emu=(1000, 500))
            with self.assertRaises(ValueError):
                rt.register({"attempt": 1, "generated_source": str(generated)})
            self.assertEqual(rt.load_state()["status"], "planned")


if __name__ == "__main__":
    unittest.main()
