"""L3b — `Space` and `FabricPlan`: what the wall graph hands to L4.

A `Space` is a face of the wall graph plus the net polygon inside it. It is
never placed: it is read off the graph, which is why it carries both its axis
polygon and its net polygon, and the list of walls that produced the difference.

Adjacency here is measured in metres of shared wall and filtered by the door
module, so `adjacency_graph()` reports where someone can actually walk rather
than where two outlines happen to touch.
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Polygon

from planfgen.brief.parcel import Parcel
from planfgen.brief.programme import RoomType
from planfgen.brief.regulation import RegulationProfile
from planfgen.fabric.axis import TOL, WallAxis, segment_overlap
from planfgen.fabric.graph import BOUND_TOL, WallGraph


def edge_run(
    wall: WallAxis,
    a: tuple[float, float],
    b: tuple[float, float],
    slack: float,
) -> float:
    """Metres of `wall` running along the segment a->b, allowing an offset.

    A facade *axis* is a centreline, so it sits half a wall inside the parcel
    boundary rather than on it. `slack` is how far off the segment the axis may
    lie and still count as being on that edge — half the facade thickness, in
    practice. Plain float arithmetic; this is called per wall per candidate.
    """
    edge_horizontal = abs(b[1] - a[1]) <= TOL
    edge_vertical = abs(b[0] - a[0]) <= TOL
    if edge_horizontal:
        if not wall.is_horizontal or abs(wall.p0[1] - a[1]) > slack:
            return 0.0
        axis = 0
    elif edge_vertical:
        if not wall.is_vertical or abs(wall.p0[0] - a[0]) > slack:
            return 0.0
        axis = 1
    else:
        return 0.0

    lo = max(min(wall.p0[axis], wall.p1[axis]), min(a[axis], b[axis]))
    hi = min(max(wall.p0[axis], wall.p1[axis]), max(a[axis], b[axis]))
    return max(0.0, hi - lo)


def _bbox_dims(polygon: Polygon) -> tuple[float, float]:
    minx, miny, maxx, maxy = polygon.bounds
    return maxx - minx, maxy - miny


@dataclass
class Space:
    """One face of the wall graph, and the habitable rectangle inside it."""

    nom: str
    kind: RoomType
    axis_polygon: Polygon
    net_polygon: Polygon
    bounding: list[WallAxis]

    @property
    def surface_utile(self) -> float:
        """Net area in m². This is the figure code minima apply to."""
        return self.net_polygon.area

    def net_dims(self) -> tuple[float, float]:
        """(w, h) of the net polygon's bounding box.

        For a rectangular space this *is* the largest inscribed rectangle, which
        is what makes the furniture gate two float comparisons.
        """
        return _bbox_dims(self.net_polygon)

    def axis_dims(self) -> tuple[float, float]:
        """(w, h) measured on the wall centrelines."""
        return _bbox_dims(self.axis_polygon)


@dataclass
class FabricPlan:
    """The wall graph, the spaces derived from it, and what they were built to."""

    graph: WallGraph
    spaces: dict[str, Space]
    parcel: Parcel
    profile: RegulationProfile

    def shared_wall_length(self, a: str, b: str) -> float:
        """Metres of wall two spaces hold in common."""
        return self.graph.shared_length(
            self.spaces[a].axis_polygon, self.spaces[b].axis_polygon
        )

    def door_capable(self, a: str, b: str) -> bool:
        """True if the shared run can host a door leaf plus both jambs.

        Contact is not access. ARCHITECTURE section 1 measured v1 reporting 7 of
        9 adjacencies where only 5 could take a door.
        """
        return self.shared_wall_length(a, b) >= self.profile.door_module

    def adjacency_graph(self) -> dict[str, list[str]]:
        """Every space mapped to the spaces one can actually reach from it."""
        noms = list(self.spaces)
        return {
            a: [b for b in noms if b != a and self.door_capable(a, b)] for a in noms
        }

    @property
    def total_utile(self) -> float:
        """Sum of the net areas actually delivered, in m²."""
        return sum(space.surface_utile for space in self.spaces.values())

    @property
    def _slack(self) -> float:
        """How far a facade axis may sit inside the boundary and still be on it."""
        return self.profile.facade_t / 2 + BOUND_TOL

    def walls_on_edge(self, space: Space, edge: int) -> list[WallAxis]:
        """The space's walls running along one numbered edge of the parcel.

        The partition is realised on the outline inset by half the facade, so a
        facade axis is parallel to its parcel edge rather than collinear with
        it. Matching therefore allows that offset — see `edge_run`.
        """
        coords = list(self.parcel.outline.exterior.coords)
        a, b = coords[edge], coords[edge + 1]
        return [
            wall
            for wall in space.bounding
            if edge_run(wall, a, b, self._slack) > BOUND_TOL
        ]

    def edge_length_on(self, space: Space, edge: int) -> float:
        """Metres this space presents to one edge of the parcel."""
        coords = list(self.parcel.outline.exterior.coords)
        a, b = coords[edge], coords[edge + 1]
        return sum(edge_run(wall, a, b, self._slack) for wall in space.bounding)

    def exterior_walls(self, space: Space) -> list[WallAxis]:
        """The space's walls that lie on the parcel outline.

        These are the only walls that can carry a window, and only where the
        edge they sit on is openable.
        """
        n = len(self.parcel.outline.exterior.coords) - 1
        found: list[WallAxis] = []
        for edge in range(n):
            for wall in self.walls_on_edge(space, edge):
                if not any(wall is seen for seen in found):
                    found.append(wall)
        return found
