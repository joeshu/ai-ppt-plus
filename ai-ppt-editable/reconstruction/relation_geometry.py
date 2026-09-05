"""Atomic geometry solving for explicitly approved ordered peer constraints.

No implicit relation expansion: caller enumerates members and locks. Connector
and containment repairs require their own evidence and are not guessed here.
"""
from copy import deepcopy
from math import isfinite


def solve_graph_relations(graph, *, locked_ids=(), confidence=.9, tolerance=1e-7):
    """Solve supported PageGraph equalities jointly with minimal movement.

    Locked nodes are equality constraints. Unsupported or uncertain relations
    are explicit blockers, never silently dropped. Containment is checked after
    solving; inconsistent/overflowing solutions are rejected atomically.
    """
    import numpy as np
    if not 0 <= confidence <= 1 or not isfinite(tolerance) or tolerance <= 0:
        raise ValueError("invalid solver confidence/tolerance")
    ids = [n.id for n in graph.nodes]
    if set(locked_ids) - set(ids):
        raise ValueError("unknown locked node")
    if not ids:
        raise ValueError("empty graph")
    offsets = {identifier: index * 4 for index, identifier in enumerate(ids)}
    initial = np.array([v for n in graph.nodes for v in n.bbox], dtype=float)
    if not np.isfinite(initial).all():
        raise ValueError("non-finite input geometry")
    rows, values, contains = [], [], []
    def equation(terms, rhs=0):
        row = np.zeros(len(initial))
        for identifier, field, weight in terms:
            row[offsets[identifier] + field] += weight
        rows.append(row)
        values.append(rhs)
    sides = {"aligned_left": [(0, 1)], "aligned_right": [(0, 1), (2, 1)],
             "aligned_top": [(1, 1)], "aligned_bottom": [(1, 1), (3, 1)],
             "aligned_center_x": [(0, 1), (2, .5)], "aligned_center_y": [(1, 1), (3, .5)],
             "equal_width": [(2, 1)], "equal_height": [(3, 1)]}
    for node in graph.nodes:
        for relation in node.relations:
            if relation.confidence < confidence:
                raise ValueError(f"uncertain relation: {node.id}/{relation.kind}")
            target = relation.target
            if relation.kind in sides:
                terms = [(node.id, field, weight) for field, weight in sides[relation.kind]]
                terms += [(target, field, -weight) for field, weight in sides[relation.kind]]
                equation(terms)
            elif relation.kind in {"contains", "belongs_to"}:
                contains.append((node.id, target) if relation.kind == "contains" else (target, node.id))
            elif relation.kind == "anchors_to":
                offset = relation.metadata.get("offset")
                if not isinstance(offset, (list, tuple)) or len(offset) != 2:
                    raise ValueError("anchor requires explicit normalized offset")
                for field in (0, 1):
                    equation([(node.id, field, 1), (target, field, -1)], float(offset[field]))
            elif relation.kind == "equal_gap":
                members = relation.metadata.get("members")
                axis = relation.metadata.get("axis")
                if axis not in {"x", "y"} or not isinstance(members, list) or len(members) < 3 or len(set(members)) != len(members) or set(members) - set(ids):
                    raise ValueError("equal gap requires explicit ordered members/axis")
                field = 0 if axis == "x" else 1
                for a, b, c in zip(members, members[1:], members[2:]):
                    equation([(c, field, 1), (b, field, -2), (b, field + 2, -1),
                              (a, field, 1), (a, field + 2, 1)])
            else:
                raise ValueError(f"unsupported relation requires explicit repair: {relation.kind}")
    for identifier in locked_ids:
        for field in range(4):
            equation([(identifier, field, 1)], initial[offsets[identifier] + field])
    solution = initial.copy()
    if rows:
        matrix, rhs = np.array(rows), np.array(values)
        if not np.isfinite(rhs).all():
            raise ValueError("non-finite relation")
        solution += np.linalg.lstsq(matrix, rhs - matrix @ initial, rcond=None)[0]
        if np.max(np.abs(matrix @ solution - rhs)) > tolerance:
            raise ValueError("inconsistent/locked relations")
    boxes = {identifier: solution[offsets[identifier]:offsets[identifier] + 4].tolist() for identifier in ids}
    for x, y, w, h in boxes.values():
        if min(x, y, w, h) < -tolerance or x + w > 1 + tolerance or y + h > 1 + tolerance:
            raise ValueError("constraint solution outside slide")
    for parent, child in contains:
        x, y, w, h = boxes[parent]
        cx, cy, cw, ch = boxes[child]
        if cx < x - tolerance or cy < y - tolerance or cx + cw > x + w + tolerance or cy + ch > y + h + tolerance:
            raise ValueError("containment violation requires reconstruction")
    changed = [n.id for n in graph.nodes if max(abs(a-b) for a,b in zip(n.bbox, boxes[n.id])) > tolerance]
    return {"boxes": boxes, "applied": changed}


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
