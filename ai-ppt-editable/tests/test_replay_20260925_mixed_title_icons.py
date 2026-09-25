from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mixed_title_render_and_icon_batch_contracts():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    dense = (ROOT / "references/dense-single-slide-reconstruction.md").read_text(encoding="utf-8")
    regressions = (ROOT / "references/image-to-editable-regressions.md").read_text(encoding="utf-8")
    assert "first fresh office render" in skill
    assert "split only at the style boundary" in dense
    assert "shared baseline" in dense
    assert "painted alpha bbox" in dense
    assert "VIS-RICH-RUN-STYLE-LOST" in regressions
    assert "VIS-ICON-BATCH-CELL-OVERFLOW" in regressions
