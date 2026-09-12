"""L8 — the numbers on the drawing.

A plan without dimensions is a picture. What makes it a drawing is that every
line has a measurement someone can build to, and the measurements come from the
same wall axes everything else came from — not from a separate model that could
disagree with the geometry.

A chain is a run of dimensions along one axis: `ticks` are the coordinates being
called out and consecutive ticks give the individual bays. Exterior chains sit
outside each facade; interior chains sit on the structural lines, which are the
only lines two levels have to agree about.
"""

from __future__ import annotations

from dataclasses import dataclass

from planfgen.fabric.axis import TOL, WallKind
from planfgen.fabric.plan import FabricPlan, Space

#: How far outside the plan an exterior chain sits, in metres.
CHAIN_OFFSET = 0.80

#: Coordinates closer than this are the same tick.
TICK_TOL = 1e-6


@dataclass(frozen=True)
class DimensionChain:
    """One run of dimensions. `axis` is what it measures along, x or y.

    `position` is where the chain line itself sits, on the other axis.
    """

    axis: str
    position: float
    ticks: list[float]

    @property
    def spans(self) -> list[float]:
        """The individual bays: what each dimension in the chain reads."""
        return [b - a for a, b in zip(self.ticks, self.ticks[1:])]

    @property
    def total(self) -> float:
        return self.ticks[-1] - self.ticks[0] if len(self.ticks) > 1 else 0.0


def _merge(values: list[float]) -> list[float]:
    """Sorted, with coordinates within tolerance collapsed to one tick."""
    out: list[float] = []
    for value in sorted(values):
        if not out or value - out[-1] > TICK_TOL:
            out.append(value)
    return out


def exterior_chains(fabric: FabricPlan) -> list[DimensionChain]:
    """One chain outside each side of the parcel.

    The ticks on a side are the walls that actually meet it, so the bottom chain
    reads the bays along the street and the top chain reads whatever the plan
    does at the back — which is usually not the same thing, and a drawing that
    showed only one of them would be hiding half the plan.
    """
    minx, miny, maxx, maxy = fabric.parcel.outline.bounds
    walls = fabric.graph.walls
    chains: list[DimensionChain] = []

    for axis, position, at, along in (
        ("x", miny - CHAIN_OFFSET, miny, True),
        ("x", maxy + CHAIN_OFFSET, maxy, True),
        ("y", minx - CHAIN_OFFSET, minx, False),
        ("y", maxx + CHAIN_OFFSET, maxx, False),
    ):
        ticks = [minx, maxx] if along else [miny, maxy]
        for wall in walls:
            if along and wall.is_vertical:
                low, high = sorted((wall.p0[1], wall.p1[1]))
                if low - CHAIN_OFFSET <= at <= high + CHAIN_OFFSET:
                    ticks.append(wall.p0[0])
            elif not along and wall.is_horizontal:
                low, high = sorted((wall.p0[0], wall.p1[0]))
                if low - CHAIN_OFFSET <= at <= high + CHAIN_OFFSET:
                    ticks.append(wall.p0[1])
        chains.append(DimensionChain(axis, position, _merge(ticks)))
    return chains


def interior_chains(fabric: FabricPlan) -> list[DimensionChain]:
    """One chain per structural line inside the plan.

    Structural means bearing, and bearing means it stacks — these are the lines
    ARCHITECTURE section 7 says two levels have to share. A plan cut entirely
    with cloisons has no interior chains, which is correct rather than empty:
    there is nothing structural in it to dimension.
    """
    minx, miny, maxx, maxy = fabric.parcel.outline.bounds
    verticals: list[float] = []
    horizontals: list[float] = []

    for wall in fabric.graph.walls:
        if wall.kind is not WallKind.PORTEUR:
            continue
        if wall.is_vertical and minx + TOL < wall.p0[0] < maxx - TOL:
            verticals.append(wall.p0[0])
        elif wall.is_horizontal and miny + TOL < wall.p0[1] < maxy - TOL:
            horizontals.append(wall.p0[1])

    chains: list[DimensionChain] = []
    for x in _merge(verticals):
        chains.append(DimensionChain("y", x, _merge([miny, maxy])))
    for y in _merge(horizontals):
        chains.append(DimensionChain("x", y, _merge([minx, maxx])))
    return chains


def room_stamp(space: Space) -> dict:
    """What gets written in the middle of a room."""
    net_w, net_h = space.net_dims()
    centroid = space.net_polygon.centroid
    return {
        "nom": space.nom,
        "kind": space.kind,
        "surface_utile": space.surface_utile,
        "net_w": net_w,
        "net_h": net_h,
        "centroid": (centroid.x, centroid.y),
    }


def stamp_text(stamp: dict) -> str:
    """The three lines of a room stamp, as they appear on the sheet."""
    return (
        f"{stamp['nom']}\\P"
        f"{stamp['surface_utile']:.2f} m2\\P"
        f"{stamp['net_w']:.2f} x {stamp['net_h']:.2f}"
    )
