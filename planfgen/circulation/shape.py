"""L5 — how much corridor, and does any of it lead nowhere.

`reachable.py` answers whether you can get there. This answers whether the
circulation is earning its keep. They are different questions and a plan can pass
the first badly: a corridor that runs the whole depth of the building and stops
blind against a facade connects every room and is still wrong.

ARCHITECTURE section 4 gives circulation a width and lets its length fall out of
the plan. Nothing then bounds that length, and `evaluate/metrics.py` scored only
the area coefficient — so a long thin spine and a compact hall of the same area
scored identically. Two things are measured here instead:

* **the stub** — how far a corridor runs past its last door. Measured from its
  ORIGIN (where it is entered: the hall, the corridor it branches off, or the
  front door if it is the way in), with each room's door on its shared run as
  near the origin as it goes — which is where L6 puts it. Since 2026-09-29 (the
  architect: "un cul de sac, c'est un espace gâché qu'on peut ajouter à une
  chambre ou à la SDB") a corridor must END at its last door.
* **run per room** — metres of circulation for each room it opens onto. A hall
  serving five rooms in six metres and a corridor serving five in fifteen are
  not the same plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from collections import deque

from planfgen.fabric.axis import WallAxis, WallKind
from planfgen.fabric.plan import FabricPlan, Space

#: Coordinates closer than this are the same point.
TOL = 1e-9


@dataclass(frozen=True)
class Run:
    """One circulation space, measured along the way you walk it."""

    nom: str
    length: float
    width: float
    served: list[str] = field(default_factory=list)
    stub: float = 0.0
    #: Where the corridor is entered, as an interval on its long axis, or None
    #: if it meets no circulation and is not the way in (reachability's problem).
    origin: tuple[float, float] | None = None

    @property
    def per_room(self) -> float:
        """Metres of corridor for each room it opens onto."""
        return self.length / len(self.served) if self.served else self.length


@dataclass(frozen=True)
class CirculationReport:
    """Every circulation space, and whether any of it leads nowhere."""

    runs: list[Run] = field(default_factory=list)

    @property
    def length(self) -> float:
        return sum(run.length for run in self.runs)

    @property
    def worst_stub(self) -> float:
        return max((run.stub for run in self.runs), default=0.0)

    @property
    def per_room(self) -> float:
        """Total circulation run over the number of rooms it serves.

        Rooms served by two arms count once: what is being asked is how much
        corridor the plan spends per room reached, not per door.
        """
        served = {nom for run in self.runs for nom in run.served}
        return self.length / len(served) if served else self.length

    def dead_ends(self, allowance: float) -> list[Run]:
        """Runs that overrun their last door by more than `allowance`."""
        return [run for run in self.runs if run.stub > allowance + TOL]

    def overrun(self, allowance: float) -> float:
        """Metres of corridor past the last doors, beyond `allowance`, summed
        over every run — what the guided walk shortens."""
        return sum(max(0.0, run.stub - allowance) for run in self.runs)

    def explain(self) -> str:
        if not self.runs:
            return "no circulation"
        head = f"{self.length:.2f} m of circulation, {self.per_room:.2f} m per room"
        blind = self.dead_ends(0.0)
        if not blind:
            return head
        return head + "; blind ends: " + ", ".join(
            f"{run.nom} overruns by {run.stub:.2f} m" for run in blind
        )


def corridor_axis(space: Space) -> int:
    """0 if a corridor runs along x, 1 if along y — its long net dimension."""
    return _axis(space)[0]


def _axis(space: Space) -> tuple[int, float, float, float]:
    """(long axis, low, high, width) of a circulation space."""
    minx, miny, maxx, maxy = space.net_polygon.bounds
    if (maxx - minx) >= (maxy - miny):
        return 0, minx, maxx, maxy - miny
    return 1, miny, maxy, maxx - minx


def _extent(wall: WallAxis, axis: int) -> tuple[float, float]:
    """A wall's extent along `axis`: its run if parallel, else the point it crosses."""
    lo, hi = sorted((wall.p0[axis], wall.p1[axis]))
    return lo, hi


def _contact(space: Space, other: Space, axis: int, end_on: float) -> tuple[float, float] | None:
    """Where `other` meets the corridor, projected on its long axis: the overlap
    of their net outlines, or — met end-on, a wall apart — the point between."""
    start = max(space.net_polygon.bounds[axis], other.net_polygon.bounds[axis])
    stop = min(space.net_polygon.bounds[axis + 2], other.net_polygon.bounds[axis + 2])
    if stop - start <= TOL:
        if start - stop > end_on + TOL:
            return None
        start = stop = (start + stop) / 2       # end-on: served where they meet
    return start, stop


def door_run(
    fabric: FabricPlan, band: str, room: str, wall: WallAxis, axis: int, module: float
) -> tuple[float, float]:
    """The stretch of `wall`, on the corridor's axis, a door between `band` and
    `room` may use: the clear floor both share, so its frame stands at the
    face of a meeting wall; the wall's whole run where the module does not fit
    that (as `openings.door.free_slot` does)."""
    a, b = fabric.spaces[band].net_polygon.bounds, fabric.spaces[room].net_polygon.bounds
    lo, hi = _extent(wall, axis)
    net_lo, net_hi = max(a[axis], b[axis], lo), min(a[axis + 2], b[axis + 2], hi)
    return (net_lo, net_hi) if net_hi - net_lo >= module - 1e-9 else (lo, hi)


def door_interval(
    run: tuple[float, float], module: float, origin: tuple[float, float]
) -> tuple[float, float]:
    """Where on the corridor's axis a door of `module` metres goes within
    `run`: as near the `origin` as it will go (centred on the origin if the
    run reaches it). L6 places the door here (`openings.place`), so the
    drawing and the gate agree."""
    lo, hi = run
    if hi - lo <= TOL or hi - lo < module:
        return lo, hi
    target = (origin[0] + origin[1]) / 2 - module / 2
    start = min(max(target, lo), hi - module)
    return start, start + module


def _hops_from_entry(fabric: FabricPlan) -> tuple[str | None, dict[str, int]]:
    """The entry, and each circulation space's hops from it over circulation."""
    from planfgen.circulation.reachable import entry_space

    try:
        entry = entry_space(fabric).nom
    except ValueError:
        return None, {}
    hops = {entry: 0}
    queue = deque([entry])
    while queue:
        current = queue.popleft()
        for nom, other in fabric.spaces.items():
            if nom in hops or not other.kind.is_circulation:
                continue
            if fabric.door_capable(current, nom):
                hops[nom] = hops[current] + 1
                queue.append(nom)
    return entry, hops


def _origin(
    fabric: FabricPlan, space: Space, axis: int, entry: str | None, hops: dict[str, int],
    end_on: float,
) -> tuple[float, float] | None:
    """Where the corridor is entered, on its long axis.

    If it is the way in, its frontage on the entry edge. Otherwise its contact
    with the circulation space nearest the entry — the hall, or the corridor it
    branches off.
    """
    if space.nom == entry:
        spans = [
            _extent(wall, axis)
            for wall in fabric.walls_on_edge(space, fabric.parcel.entry_edge)
            if wall.kind is WallKind.FACADE
        ]
        if spans:
            return min(lo for lo, _ in spans), max(hi for _, hi in spans)
    best = None
    for nom, other in fabric.spaces.items():
        if other is space or nom not in hops or not fabric.door_capable(space.nom, nom):
            continue
        contact = _contact(space, other, axis, end_on)
        if contact is not None and (best is None or hops[nom] < best[0]):
            best = (hops[nom], contact)
    return None if best is None else best[1]


def _reach(
    fabric: FabricPlan, space: Space, axis: int, origin: tuple[float, float] | None,
    end_on: float,
) -> tuple[float, float] | None:
    """The stretch of the corridor's long axis that has to exist: from its
    origin to the farthest opening, each room's door as near the origin as its
    shared run allows, each other circulation space where it meets this one.

    With no origin (a corridor nobody enters — reachability refuses it anyway)
    every contact counts over its whole run, which is the measure before
    2026-09-29.
    """
    low = high = None
    if origin is not None:
        low, high = origin
    for nom, other in fabric.spaces.items():
        if other is space or not fabric.door_capable(space.nom, nom):
            continue
        if other.kind.is_circulation or origin is None:
            span = _contact(space, other, axis, end_on)
            if span is None:
                continue
        else:
            wall = fabric.graph.wall_between(space.axis_polygon, other.axis_polygon)
            if wall is None:
                continue
            module = fabric.opening_run(space.nom, nom)
            lo, hi = _extent(wall, axis)
            if hi - lo <= TOL:                      # across the end: served at the end
                span = _contact(space, other, axis, end_on) or (lo, hi)
            else:
                span = door_interval(door_run(fabric, space.nom, nom, wall, axis, module),
                                     module, origin)
        low = span[0] if low is None else min(low, span[0])
        high = span[1] if high is None else max(high, span[1])
    return None if low is None else (low, high)


def circulation_runs(fabric: FabricPlan) -> CirculationReport:
    """Measure every circulation space: what it serves, and what it wastes."""
    runs: list[Run] = []
    # Two net outlines meeting end-on are one wall apart; never more than the
    # thickest wall the profile builds.
    end_on = max(fabric.profile.thickness_of(kind.value) for kind in WallKind)
    entry, hops = _hops_from_entry(fabric)

    for nom, space in fabric.spaces.items():
        # A hall is a room that happens to be passable, not a corridor: it has
        # an area target and a furniture spec, and a front door at one end is
        # not a run past its last door.
        if not space.kind.names_band:
            continue
        axis, low, high, width = _axis(space)
        served = sorted(
            other
            for other in fabric.spaces
            if other != nom
            and not fabric.spaces[other].kind.is_circulation
            and fabric.door_capable(nom, other)
        )
        origin = _origin(fabric, space, axis, entry, hops, end_on)
        reach = _reach(fabric, space, axis, origin, end_on)
        if reach is None:
            stub = high - low
        else:
            stub = max(reach[0] - low, high - reach[1], 0.0)
        runs.append(Run(nom, high - low, width, served, stub, origin))

    return CirculationReport(sorted(runs, key=lambda r: r.nom))
