"""Actual writer -> LibreOffice -> PDF regression, no mock measurements."""
import sys
from pathlib import Path
from copy import deepcopy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reconstruction.render_measure import measure_text
from reconstruction.repair_executors import execute_typography_search


def calibrate_case(deck, object_id, target_size, *, tolerance=.0001):
    target_deck = deepcopy(deck)
    target_deck["slides"][0]["texts"][0]["size"] = target_size
    target = measure_text(target_deck, object_id)
    assert target["font_verified"] and target["copy_valid"] and not target["overflow"], target
    result = execute_typography_search(deck, object_id, target, [{"font_size": target_size}], measure_text, tolerance=tolerance)
    assert result["report"]["valid"], result
    assert result["report"]["search"]["render_calls"] == 2
    assert result["deck"]["slides"][0]["texts"][0]["size"] == target_size
    return result, target


def main():
    deck = {"assets_dir": ".", "units": "fraction", "slide_width_in": 13.333333,
            "slide_height_in": 7.5, "theme": {"font": "DejaVu Sans"}, "slides": [{"texts": [
                {"object_id": "title", "x": .1, "y": .2, "w": .8, "h": .4,
                 "size": 24, "font": "DejaVu Sans", "text": "Revenue growth",
                 "runs": [{"text": "Revenue ", "color": "FF0000"}, {"text": "growth", "bold": True}]}]}]}
    result, _ = calibrate_case(deck, "title", 30)
    assert deck["slides"][0]["texts"][0]["size"] == 24
    assert result["deck"]["slides"][0]["texts"][0]["runs"] == deck["slides"][0]["texts"][0]["runs"]

    # Match the family declared by assets/fonts/font-manifest.json.  Give the
    # fixture an explicit top inset so the target render itself is a valid,
    # non-overflow typography specimen; the gate remains fail-closed.
    cjk_family = "Noto Sans CJK SC"
    zh = {"assets_dir": ".", "units": "fraction", "slide_width_in": 13.333333,
          "slide_height_in": 7.5, "theme": {"font": cjk_family}, "slides": [{"texts": [
              {"object_id": "zh-title", "x": .08, "y": .10, "w": .84, "h": .42,
               "margin_top": 24, "size": 22, "font": cjk_family, "text": "存量用户价值提升 2026",
               "runs": [{"text": "存量用户", "bold": True},
                        {"text": "价值提升 ", "color": "D71920"},
                        {"text": "2026", "bold": True}]}]}]}
    zh_result, zh_target = calibrate_case(zh, "zh-title", 28, tolerance=.0002)
    assert zh_target["line_count"] >= 1
    assert zh_target["font_verified"] is True
    assert zh_target["copy_valid"] is True
    assert zh_target["overflow"] is False
    assert zh_result["deck"]["slides"][0]["texts"][0]["runs"] == zh["slides"][0]["texts"][0]["runs"]
    assert "存量用户" in zh_result["deck"]["slides"][0]["texts"][0]["text"]
    print("PASS actual LibreOffice typography correction for Latin and Chinese mixed rich text")


if __name__ == "__main__":
    main()
