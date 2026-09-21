import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_final_asset_isolation import validate_deck_asset_isolation


class FinalAssetIsolationTests(unittest.TestCase):
    def _layout(self, root: Path, icon: str) -> tuple[Path, dict]:
        assets = root / "final-assets"
        assets.mkdir(parents=True, exist_ok=True)
        deck = {
            "assets_dir": str(assets),
            "slides": [{"icons": [{"object_id": "hero-icon", "file": icon, "x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1}]}],
        }
        layout = root / "layout.json"
        layout.write_text(json.dumps(deck), encoding="utf-8")
        return layout, deck

    def test_clean_final_asset_directory_passes(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            layout, deck = self._layout(root, "hero.png")
            (root / "final-assets" / "hero.png").write_bytes(b"png")
            report = validate_deck_asset_isolation(deck, layout)
            self.assertTrue(report["valid"], report)
            self.assertEqual(report["referenced_asset_count"], 1)

    def test_contact_sheet_in_final_tree_blocks_even_if_not_referenced(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            layout, deck = self._layout(root, "hero.png")
            assets = root / "final-assets"
            (assets / "hero.png").write_bytes(b"png")
            (assets / "contact_sheet.png").write_bytes(b"png")
            report = validate_deck_asset_isolation(deck, layout)
            self.assertFalse(report["valid"])
            self.assertIn("qa_assets_co_located_with_final_assets", {item["code"] for item in report["errors"]})

    def test_debug_crop_reference_blocks(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            layout, deck = self._layout(root, "debug-crops/icon.png")
            debug = root / "final-assets" / "debug-crops"
            debug.mkdir(parents=True)
            (debug / "icon.png").write_bytes(b"png")
            report = validate_deck_asset_isolation(deck, layout)
            self.assertFalse(report["valid"])
            self.assertIn("qa_asset_referenced_by_deck", {item["code"] for item in report["errors"]})

    def test_qa_root_cannot_be_final_assets_dir(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            qa = root / "qa"
            qa.mkdir()
            (qa / "hero.png").write_bytes(b"png")
            deck = {"assets_dir": str(qa), "slides": [{"icons": [{"file": "hero.png"}]}]}
            layout = root / "layout.json"
            layout.write_text(json.dumps(deck), encoding="utf-8")
            report = validate_deck_asset_isolation(deck, layout)
            self.assertFalse(report["valid"])
            self.assertIn("final_asset_root_is_qa_directory", {item["code"] for item in report["errors"]})

    def test_legacy_project_root_does_not_scan_unreferenced_qa(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            qa = root / "qa"
            qa.mkdir()
            (qa / "comparison.png").write_bytes(b"png")
            deck = {"assets_dir": str(root), "_assets_dir_explicit": False, "slides": [{"texts": [{"text": "native"}]}]}
            layout = root / "layout.json"
            layout.write_text(json.dumps(deck), encoding="utf-8")
            report = validate_deck_asset_isolation(deck, layout)
            self.assertTrue(report["valid"], report)
            self.assertFalse(report["scan_tree"])


if __name__ == "__main__":
    unittest.main()
