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
from planfgen.fabric.axis import WallAxis, segment_overlap
from planfgen.fabric.graph import BOUND_TOL, WallGraph


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

    def exterior_walls(self, space: Space) -> list[WallAxis]:
        """The space's walls that lie on the parcel outline.

        These are the only walls that can carry a window, and only where the
        edge they sit on is openable.
        """
        coords = list(self.parcel.outline.exterior.coords)
        outline = [(coords[i], coords[i + 1]) for i in range(len(coords) - 1)]
        return [
            wall
            for wall in space.bounding
            if any(
                segment_overlap(wall.p0, wall.p1, a, b) > BOUND_TOL for a, b in outline
            )
        ]
