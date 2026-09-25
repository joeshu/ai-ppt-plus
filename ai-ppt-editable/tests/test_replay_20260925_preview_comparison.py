from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_preview_comparison_text_icon_and_canvas_contracts():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    dense = (ROOT / "references/dense-single-slide-reconstruction.md").read_text(encoding="utf-8")
    regressions = (ROOT / "references/image-to-editable-regressions.md").read_text(encoding="utf-8")

    assert "PPTX page-size record" in skill
    assert "1921 x 1080" in skill
    assert "role-specific font floor" in skill
    assert "blank-space ratio" in dense
    assert "Allocate the densest" in dense and "card first" in dense
    assert "visible-height ratio" in dense
    assert "VIS-RENDER-PIXEL-ROUNDING" in regressions
    assert "VIS-TEXT-DENSITY-DRIFT" in regressions
    assert "VIS-ICON-PAINTED-SCALE-DRIFT" in regressions
