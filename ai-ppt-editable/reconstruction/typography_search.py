"""Bounded typography search using measurements from the actual host renderer.

No Pillow font surrogate: the callback must author/render the trial and return
its measured ink bbox, line count, baseline positions and font evidence.
"""
from copy import deepcopy
from math import isfinite


ALLOWED = {"font", "font_size", "size", "line_spacing", "margin_left", "margin_right",
           "margin_top", "margin_bottom", "bold", "italic"}


def _vector(value, length):
    if not isinstance(value, (tuple, list)) or len(value) != length:
        raise ValueError("invalid measurement vector")
    result = [float(v) for v in value]
    if not all(isfinite(v) for v in result):
        raise ValueError("non-finite measurement")
    return result


def measurement_loss(target, observed):
    if target.get("measurement_kind") and target["measurement_kind"] != observed.get("measurement_kind"):
        raise ValueError("target and render must use the same measurement kind")
    if observed.get("font_verified") is not True or observed.get("overflow") is not False:
        return None
    if observed.get("line_count") != target["line_count"]:
        return None
    expected = _vector(target["ink_bbox"], 4)
    actual = _vector(observed["ink_bbox"], 4)
    baselines = _vector(target["baselines"], target["line_count"])
    measured = _vector(observed["baselines"], target["line_count"])
    return max([abs(a - b) for a, b in zip(expected, actual)] +
               [abs(a - b) for a, b in zip(baselines, measured)])


def calibrate_typography(text_object, target, patches, render_measure, *, budget=12, tolerance=.002):
    """Return an isolated best candidate, never silently shrink to fit.

    Coordinates are normalized slide fractions. Candidate patches are explicit
    proposals; unsupported properties and text/run modifications are rejected.
    Trial zero is always the unchanged object and consumes the same budget.
    """
    if not isinstance(budget, int) or budget < 1 or not isfinite(tolerance) or tolerance < 0:
        raise ValueError("invalid search budget/tolerance")
    trials, best = [], None
    for patch in [{}] + list(patches)[:budget - 1]:
        if set(patch) - ALLOWED:
            raise ValueError("typography patch may not change copy, runs or geometry")
        candidate = deepcopy(text_object)
        candidate.update(deepcopy(patch))
        if "font_size" in patch:
            if "size" in patch and patch["size"] != patch["font_size"]:
                raise ValueError("conflicting size aliases")
            candidate["size"] = patch["font_size"]
        for key in ("size", "font_size", "line_spacing"):
            if key in patch and (isinstance(patch[key], bool) or not isfinite(float(patch[key])) or float(patch[key]) <= 0):
                raise ValueError(f"invalid {key}")
        for key in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
            if key in patch and (isinstance(patch[key], bool) or not isfinite(float(patch[key])) or float(patch[key]) < 0):
                raise ValueError(f"invalid {key}")
        evidence = render_measure(deepcopy(candidate))
        if not evidence.get("render_sha256") or not evidence.get("renderer"):
            raise ValueError("actual renderer/hash evidence required")
        score = measurement_loss(target, evidence)
        trials.append({"patch": deepcopy(patch), "loss": score, "evidence": evidence})
        if score is not None and (best is None or score < best["loss"]):
            best = {"object": candidate, "loss": score, "patch": deepcopy(patch)}
        if score is not None and score <= tolerance:
            break
    return {"status": "accepted" if best is not None and best["loss"] <= tolerance else "needs-review",
            "best": best, "trials": trials, "render_calls": len(trials)}
