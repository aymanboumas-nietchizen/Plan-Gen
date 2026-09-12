"""L4 — shafts, as objects with positions.

ARCHITECTURE section 7: a shaft is not a property of a room. If it were, two
levels could not be asked whether their shafts line up, because there would be
nothing to compare — only rooms, which move. Making it an object with x and y is
one of the three things that cost nothing now and are expensive to retrofit.

A plumbing shaft wants to serve as many wet rooms as it can from one position,
so it is sited on a wall two wet rooms share wherever there is one. Where a wet
room stands alone it goes on that room's least useful wall: a party wall or a
setback first, since neither could have carried a window anyway, and otherwise
the wall the room shares least with its neighbours.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum

from planfgen.brief.regulation import RegulationProfile
from planfgen.fabric.axis import WallAxis
from planfgen.fabric.plan import FabricPlan

#: Side of a shaft, in metres. A *conventional placeholder*, like the numbers in
#: `brief/regulation.py` and `habitability/furniture.py`, and not a verified
#: requirement: a real plumbing duct is sized from the stack it carries.
SHAFT_SIDE = 0.30


class ShaftType(Enum):
    """What runs up it."""

    PLUMBING = "plumbing"
    VENTILATION = "ventilation"
    ELECTRICAL = "electrical"


@dataclass
class Shaft:
    """A vertical duct, positioned. `x, y` is the lower-left corner.

    Mutable because `stack_id` is assigned later, by `assign_stack_ids`, once a
    grid is known — the same reason `WallAxis` is mutable.
    """

    x: float
    y: float
    w: float
    h: float
    kind: ShaftType
    stack_id: str = ""

    @property
    def centre(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)

    def on_wall(self, wall: WallAxis, slack: float = SHAFT_SIDE) -> bool:
        """True if this shaft sits on that wall's run."""
        cx, cy = self.centre
        (x0, y0), (x1, y1) = wall.p0, wall.p1
        if wall.is_horizontal:
            return abs(cy - y0) <= slack and min(x0, x1) - slack <= cx <= max(x0, x1) + slack
        return abs(cx - x0) <= slack and min(y0, y1) - slack <= cy <= max(y0, y1) + slack


def wet_clusters(fabric: FabricPlan) -> list[list[str]]:
    """Wet rooms grouped by whether they touch, in a stable order.

    Touching is enough — a wet wall carries no door, so `door_capable` is the
    wrong question here.
    """
    wet = sorted(nom for nom, space in fabric.spaces.items() if space.kind.is_wet)
    seen: set[str] = set()
    clusters: list[list[str]] = []
    for start in wet:
        if start in seen:
            continue
        group, queue = [start], deque([start])
        seen.add(start)
        while queue:
            current = queue.popleft()
            for other in wet:
                if other in seen:
                    continue
                if fabric.shared_wall_length(current, other) > 0:
                    seen.add(other)
                    group.append(other)
                    queue.append(other)
        clusters.append(sorted(group))
    return clusters


def _shared_wall(fabric: FabricPlan, cluster: list[str]) -> WallAxis | None:
    """The longest wall two rooms of the cluster hold in common."""
    best: WallAxis | None = None
    for i, a in enumerate(cluster):
        for b in cluster[i + 1 :]:
            wall = fabric.graph.wall_between(
                fabric.spaces[a].axis_polygon, fabric.spaces[b].axis_polygon
            )
            if wall is not None and (best is None or wall.length > best.length):
                best = wall
    return best


def _least_used_wall(fabric: FabricPlan, nom: str) -> WallAxis:
    """The wall of a lone wet room that costs least to occupy.

    A party wall or a setback ranks first: it could not have taken a window, so
    a duct against it gives nothing up. Otherwise the wall the room shares least
    with its neighbours, longest first so the shaft has somewhere to sit.
    """
    space = fabric.spaces[nom]
    parcel = fabric.parcel
    blind = set()
    for edge in range(len(parcel.outline.exterior.coords) - 1):
        if not parcel.openable(edge):
            blind.update(id(w) for w in fabric.walls_on_edge(space, edge))

    def use(wall: WallAxis) -> tuple[int, float, float]:
        shared = sum(
            fabric.graph.shared_length(space.axis_polygon, other.axis_polygon)
            for other_nom, other in fabric.spaces.items()
            if other_nom != nom
        )
        return (0 if id(wall) in blind else 1, shared, -wall.length)

    return min(sorted(space.bounding, key=lambda w: (w.p0, w.p1)), key=use)


def _shaft_on(wall: WallAxis, kind: ShaftType) -> Shaft:
    """A square duct straddling the wall at its midpoint."""
    cx = (wall.p0[0] + wall.p1[0]) / 2
    cy = (wall.p0[1] + wall.p1[1]) / 2
    half = SHAFT_SIDE / 2
    return Shaft(cx - half, cy - half, SHAFT_SIDE, SHAFT_SIDE, kind)


def place_shafts(fabric: FabricPlan, profile: RegulationProfile) -> list[Shaft]:
    """One plumbing shaft per wet cluster.

    Sited on a wall two wet rooms share where the cluster has one, so a single
    stack serves both; otherwise on the lone room's least useful wall.
    """
    shafts: list[Shaft] = []
    for cluster in wet_clusters(fabric):
        wall = _shared_wall(fabric, cluster)
        if wall is None:
            wall = _least_used_wall(fabric, cluster[0])
        shafts.append(_shaft_on(wall, ShaftType.PLUMBING))
    return shafts
