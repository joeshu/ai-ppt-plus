import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from enforce_ooxml_font_faces import enforce


def test_binds_latin_east_asian_and_complex_script_slots(tmp_path):
    source = tmp_path / "source.pptx"
    output = tmp_path / "output.pptx"
    xml = (
        '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:rPr><a:latin typeface="Arial"/></a:rPr></p:sld>'
    ).encode()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", xml)
    report = enforce(source, output, family="Noto Sans CJK SC")
    assert report["changed_text_properties"] == 1
    with zipfile.ZipFile(output) as archive:
        text = archive.read("ppt/slides/slide1.xml").decode()
    assert text.count('typeface="Noto Sans CJK SC"') == 3


def test_rejects_missing_input(tmp_path):
    try:
        enforce(tmp_path / "missing.pptx", tmp_path / "out.pptx", family="Noto Sans CJK SC")
    except FileNotFoundError:
        return
    raise AssertionError("missing OOXML input must fail closed")
