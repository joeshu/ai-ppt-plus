"""Atomic geometry solving for explicitly approved ordered peer constraints.

No implicit relation expansion: caller enumerates members and locks. Connector
and containment repairs require their own evidence and are not guessed here.
"""
from copy import deepcopy
from math import isfinite


def solve_peer_layout(objects, member_ids, *, axis="x", start, end,
                      equal_size=False, locked_ids=(), tolerance=1e-9):
    if axis not in {"x", "y"} or len(member_ids) < 2 or len(set(member_ids)) != len(member_ids):
        raise ValueError("ordered distinct peers and x/y axis required")
    if not all(isfinite(v) for v in (start, end, tolerance)) or not 0 <= start < end <= 1 or tolerance < 0:
        raise ValueError("invalid normalized interval")
    result = deepcopy(objects)
    dimension = "w" if axis == "x" else "h"
    widths = [float(result[i][dimension]) for i in member_ids]
    if any(not isfinite(w) or w <= 0 for w in widths):
        raise ValueError("invalid peer size")
    if equal_size:
        widths = [sum(widths) / len(widths)] * len(widths)
    gap = (end - start - sum(widths)) / (len(widths) - 1)
    if gap < -tolerance:
        raise ValueError("peers do not fit; refusing implicit shrinking")
    cursor = start
    applied = []
    for identifier, size in zip(member_ids, widths):
        old = result[identifier]
        changed = abs(old[axis] - cursor) > tolerance or abs(old[dimension] - size) > tolerance
        if changed and identifier in locked_ids:
            raise ValueError(f"constraint conflicts with accepted lock: {identifier}")
        if changed:
            old[axis], old[dimension] = cursor, size
            applied.append(identifier)
        cursor += size + gap
    return {"objects": result, "applied": applied, "gap": gap}
