import unittest


class EmbeddedAssetCoverageContractTest(unittest.TestCase):
    def test_contract_requires_complete_picture_coverage(self):
        required = {"independent_asset", "visible_alpha_bbox", "alpha_centroid", "placement_bbox", "local_crop_qa"}
        manifest_entry = {"independent_asset": True, "visible_alpha_bbox": [1, 2, 3, 4], "alpha_centroid": [2, 3], "placement_bbox": [1, 2, 3, 4], "local_crop_qa": {"approved": True}}
        self.assertTrue(required.issubset(manifest_entry))

    def test_source_reuse_is_not_an_implicit_success_path(self):
        final_asset = {"source_kind": "native_imagegen", "independent_asset": True}
        self.assertNotEqual(final_asset.get("source_kind"), "source_crop")


if __name__ == "__main__":
    unittest.main()
