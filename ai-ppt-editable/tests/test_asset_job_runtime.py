import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from reconstruction.asset_job_runtime import AssetJobRuntime


class AssetJobRuntimeTest(unittest.TestCase):
    def _job(self):
        return {"asset_id": "icon-a", "cache_key": "abc", "request": {"object_id": "icon-a", "background_mode": "transparent", "preserve_geometry": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}}}

    def test_register_review_and_cache_hit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.png"
            generated = root / "generated.png"
            Image.new("RGB", (64, 64), "white").save(source)
            im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            for x in range(16, 48):
                for y in range(16, 48):
                    im.putpixel((x, y), (220, 0, 20, 255))
            im.save(generated)
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
            im = Image.new("RGBA", (64, 64), (0, 0, 0, 0)); im.putpixel((32, 32), (0, 0, 255, 255)); im.save(generated)
            rt = AssetJobRuntime(self._job(), root, source, slide_size_emu=(1000, 500))
            rt.register({"attempt": 1, "generated_source": str(generated)})
            state = rt.review({"review": {"approved": False, "issue_codes": ["shape_mismatch"]}})
            self.assertEqual(state["status"], "retry_required")
            self.assertEqual(state["retry_scope"], "asset_only")


if __name__ == "__main__":
    unittest.main()
