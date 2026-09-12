"""L3a — the wall graph, and the faces that fall out of it.

This is the module that makes CLAUDE.md's one rule operational: walls are
authored into the graph, and a space is read back out of it as a *face*. Nothing
here places a room. `split_at_crossings` nodes the authored axes into a planar
straight-line graph; `faces` then reads the minimal cycles off it.

Splitting and overlap are plain float arithmetic. Shapely appears only to
polygonize the noded segments and to carry the resulting faces.
"""

from __future__ import annotations

from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize

from planfgen.fabric.axis import TOL, WallAxis, segment_overlap

#: A face edge and a wall must share more than this to count as bounding it.
BOUND_TOL = 1e-6


def _span(wall: WallAxis) -> tuple[bool, float, float, float]:
    """(is_horizontal, fixed coordinate, low, high) along the wall's free axis."""
    if wall.is_horizontal:
        return True, wall.p0[1], min(wall.p0[0], wall.p1[0]), max(wall.p0[0], wall.p1[0])
    return False, wall.p0[0], min(wall.p0[1], wall.p1[1]), max(wall.p0[1], wall.p1[1])


def _face_edges(face: Polygon) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    coords = list(face.exterior.coords)
    return [(coords[i], coords[i + 1]) for i in range(len(coords) - 1)]


class WallGraph:
    """A set of wall axes, and the faces they enclose."""

    def __init__(self, walls: list[WallAxis] | None = None):
        self.walls: list[WallAxis] = list(walls) if walls else []

    def add(self, wall: WallAxis) -> None:
        self.walls.append(wall)

    def split_at_crossings(self) -> None:
        """Node the graph in place: no axis crosses or ends inside another.

        For axis-aligned input two cases cover every junction. A perpendicular
        pair meets at one point, which splits whichever of the two contains it
        in its interior — this catches both crossings and T-junctions. A
        collinear pair contributes the ends of its shared run, which catches an
        axis that starts or stops partway along another.

        Split segments inherit their parent's kind and stack id. Duplicate
        segments are dropped, so an axis authored twice bounds a face once.
        """
        spans = [_span(w) for w in self.walls]
        split: list[WallAxis] = []
        seen: set[tuple[tuple[float, float], tuple[float, float]]] = set()

        for i, wall in enumerate(self.walls):
            w_h, w_fixed, w_lo, w_hi = spans[i]
            cuts = [w_lo, w_hi]

            for j, (o_h, o_fixed, o_lo, o_hi) in enumerate(spans):
                if i == j:
                    continue
                if w_h == o_h:
                    if abs(w_fixed - o_fixed) > TOL:
                        continue
                    cuts.append(max(w_lo, o_lo))
                    cuts.append(min(w_hi, o_hi))
                else:
                    # Perpendicular: they meet where each one's fixed coordinate
                    # crosses the other's free axis.
                    if not (o_lo - TOL <= w_fixed <= o_hi + TOL):
                        continue
                    cuts.append(o_fixed)

            inside = sorted(c for c in cuts if w_lo - TOL <= c <= w_hi + TOL)
            merged = [w_lo]
            for c in inside:
                if c - merged[-1] > TOL:
                    merged.append(c)
            if merged[-1] < w_hi - TOL:
                merged.append(w_hi)

            for a, b in zip(merged, merged[1:]):
                if b - a <= TOL:
                    continue
                p0 = (a, w_fixed) if w_h else (w_fixed, a)
                p1 = (b, w_fixed) if w_h else (w_fixed, b)
                key = (p0, p1)
                if key in seen:
                    continue
                seen.add(key)
                split.append(WallAxis(p0, p1, wall.kind, wall.stack_id))

        self.walls = split

    def faces(self) -> list[Polygon]:
        """The minimal faces enclosed by the walls.

        Assumes the graph is already noded — call `split_at_crossings` first.
        Polygonize returns minimal cycles only, but any polygon that turns out
        to contain another is dropped anyway, so the exterior can never be
        mistaken for a space.
        """
        polys = list(polygonize(LineString([w.p0, w.p1]) for w in self.walls))
        if len(polys) < 2:
            return polys
        return [
            p
            for p in polys
            if not any(
                q is not p and p.contains(q.representative_point()) for q in polys
            )
        ]

    def bounding_walls(self, face: Polygon) -> list[WallAxis]:
        """Every axis that runs along an edge of this face."""
        edges = _face_edges(face)
        return [
            wall
            for wall in self.walls
            if any(
                segment_overlap(wall.p0, wall.p1, a, b) > BOUND_TOL for a, b in edges
            )
        ]

    def wall_between(self, face_a: Polygon, face_b: Polygon) -> WallAxis | None:
        """The axis these two faces share, longest first, or None if they do not.

        Faces meeting at a single corner share no wall: a point is not a run.
        """
        in_b = {id(w) for w in self.bounding_walls(face_b)}
        common = [w for w in self.bounding_walls(face_a) if id(w) in in_b]
        if not common:
            return None
        return max(common, key=lambda w: w.length)

    def shared_length(self, face_a: Polygon, face_b: Polygon) -> float:
        """Metres of boundary the two faces hold in common.

        This is the measurement CLAUDE.md requires adjacency to be made of: two
        spaces are connectable only if this exceeds the door module, however
        close their outlines come elsewhere.
        """
        edges_b = _face_edges(face_b)
        return sum(
            segment_overlap(a, b, c, d)
            for a, b in _face_edges(face_a)
            for c, d in edges_b
        )
