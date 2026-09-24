from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dense_replay_guards_contrast_bullets_and_decode_fallback():
    regressions = (ROOT / "references/image-to-editable-regressions.md").read_text()
    dense = (ROOT / "references/dense-single-slide-reconstruction.md").read_text()

    assert "bullet anchor per paragraph" in regressions
    assert "high-contrast variant" in regressions
    assert "native color underlay" in regressions
    assert "compact, ordinary or dense" in dense
    assert "Batch semantically related ImageGen icons" in dense
