"""Actual writer -> LibreOffice -> PDF regression, no mock measurements."""
import sys
from pathlib import Path
from copy import deepcopy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reconstruction.render_measure import measure_text
from reconstruction.repair_executors import execute_typography_search


def main():
    deck = {"assets_dir": ".", "units": "fraction", "slide_width_in": 13.333333,
            "slide_height_in": 7.5, "theme": {"font": "DejaVu Sans"}, "slides": [{"texts": [
                {"object_id": "title", "x": .1, "y": .2, "w": .8, "h": .4,
                 "size": 24, "font": "DejaVu Sans", "text": "Revenue growth",
                 "runs": [{"text": "Revenue ", "color": "FF0000"}, {"text": "growth", "bold": True}]}]}]}
    target_deck = deepcopy(deck)
    target_deck["slides"][0]["texts"][0]["size"] = 30
    target = measure_text(target_deck, "title")
    assert target["font_verified"] and target["copy_valid"] and not target["overflow"], target
    result = execute_typography_search(deck, "title", target, [{"font_size": 30}], measure_text, tolerance=.0001)
    assert result["report"]["valid"], result
    assert result["report"]["search"]["render_calls"] == 2
    assert result["deck"]["slides"][0]["texts"][0]["size"] == 30
    assert deck["slides"][0]["texts"][0]["size"] == 24
    assert result["deck"]["slides"][0]["texts"][0]["runs"] == deck["slides"][0]["texts"][0]["runs"]
    print("PASS actual LibreOffice typography correction 24pt -> 30pt with rich text preserved")


if __name__ == "__main__":
    main()
