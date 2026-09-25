from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_standard_widescreen_and_dense_text_icon_contracts():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    dense = (ROOT / "references/dense-single-slide-reconstruction.md").read_text(encoding="utf-8")
    regressions = (ROOT / "references/image-to-editable-regressions.md").read_text(encoding="utf-8")

    assert "12192000 x 6858000 EMU" in skill
    assert "1280 x 720" in dense
    assert "non-standard `16 x 9 in`" in dense
    assert "visible alpha bounds and optical center" in dense
    assert "shared baseline" in regressions
    assert "scale by painted" in regressions and "height" in regressions
