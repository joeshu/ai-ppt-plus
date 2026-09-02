"""Regression coverage for the imagegen sheet slicing contract."""
from pathlib import Path

def test_sheet_slicing_reference_exists():
    root = Path(__file__).parents[1]
    ref = root / "references" / "imagegen-sheet-slicing.md"
    assert ref.exists()
    text = ref.read_text(encoding="utf-8")
    for marker in ("uniform_grid", "variable_row", "artistic_row", "4x4"):
        assert marker in text
