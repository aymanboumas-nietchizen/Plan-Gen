"""L3b — giving the centreline graph its thickness.

ARCHITECTURE section 2: a space loses half the thickness of each wall bounding
it, so `net_w = axis_w - (t_left + t_right) / 2`. The correction is exact and
needs no iteration, because the graph already knows which wall sits on which
edge before the area is measured.

The inward offset is done with float arithmetic on the edges. Shapely's
`buffer` is not an option: on a negative buffer it would round or mitre the
corners, and a 3.00 m room would come out a few square centimetres short of the
closed form the whole net/gross contract rests on.
"""

from __future__ import annotations

import math

from shapely.geometry import Polygon

from planfgen.brief.regulation import RegulationProfile
from planfgen.fabric.axis import TOL, WallAxis, segment_overlap
from planfgen.fabric.graph import BOUND_TOL


def _edges(face: Polygon) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    coords = list(face.exterior.coords)
    return [(coords[i], coords[i + 1]) for i in range(len(coords) - 1)]


def _wall_on_edge(
    edge: tuple[tuple[float, float], tuple[float, float]], bounding: list[WallAxis]
) -> WallAxis:
    """The bounding wall that runs along this face edge.

    A noded graph gives every face a vertex at every node, so each face edge is
    exactly one wall segment and the best overlap is unambiguous.
    """
    best, best_overlap = None, BOUND_TOL
    for wall in bounding:
        overlap = segment_overlap(wall.p0, wall.p1, *edge)
        if overlap > best_overlap:
            best, best_overlap = wall, overlap
    if best is None:
        raise ValueError(
            f"face edge {edge[0]} -> {edge[1]} has no bounding wall; the graph "
            f"and the face disagree"
        )
    return best


def net_polygon(
    face: Polygon, bounding: list[WallAxis], profile: RegulationProfile
) -> Polygon:
    """The habitable polygon inside a face, each edge pulled in by half its wall.

    Works on any rectilinear face, not just rectangles: every edge is offset
    along its own inward normal and the corners are recovered by intersecting
    consecutive offset lines. Two collinear edges carrying walls of different
    thickness produce a genuine step, which is emitted as a jog rather than
    smoothed away.
    """
    edges = _edges(face)
    inward = 1.0 if face.exterior.is_ccw else -1.0

    # Each edge becomes the line it offsets onto: ("h", y) or ("v", x).
    lines: list[tuple[str, float]] = []
    for edge in edges:
        (x0, y0), (x1, y1) = edge
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        nx, ny = -inward * uy, inward * ux
        half = profile.thickness_of(_wall_on_edge(edge, bounding).kind.value) / 2.0
        if abs(dy) <= TOL:
            lines.append(("h", y0 + ny * half))
        else:
            lines.append(("v", x0 + nx * half))

    n = len(lines)
    points: list[tuple[float, float]] = []
    for i in range(n):
        cur, nxt = lines[i], lines[(i + 1) % n]
        shared = edges[i][1]
        if cur[0] != nxt[0]:
            points.append((nxt[1], cur[1]) if cur[0] == "h" else (cur[1], nxt[1]))
        elif abs(cur[1] - nxt[1]) > TOL:
            # Collinear edges of unequal thickness: step across at the shared node.
            if cur[0] == "h":
                points.append((shared[0], cur[1]))
                points.append((shared[0], nxt[1]))
            else:
                points.append((cur[1], shared[1]))
                points.append((nxt[1], shared[1]))
    return Polygon(points)


def wall_solids(
    graph, profile: RegulationProfile
) -> list[tuple[WallAxis, Polygon]]:
    """Each axis paired with its solid: a rectangle of length x thickness.

    The rectangle is centred on the axis line and stops at its ends, so solids
    of walls meeting at a corner abut rather than overlap.
    """
    solids = []
    for wall in graph.walls:
        half = profile.thickness_of(wall.kind.value) / 2.0
        (x0, y0), (x1, y1) = wall.p0, wall.p1
        if wall.is_horizontal:
            box = [
                (x0, y0 - half),
                (x1, y0 - half),
                (x1, y0 + half),
                (x0, y0 + half),
            ]
        else:
            box = [
                (x0 - half, y0),
                (x0 + half, y0),
                (x0 + half, y1),
                (x0 - half, y1),
            ]
        solids.append((wall, Polygon(box)))
    return solids
