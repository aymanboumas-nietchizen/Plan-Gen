"""L5 — how much corridor, and does any of it lead nowhere.

`reachable.py` answers whether you can get there. This answers whether the
circulation is earning its keep. They are different questions and a plan can pass
the first badly: a corridor that runs the whole depth of the building and stops
blind against a facade connects every room and is still wrong.

ARCHITECTURE section 4 gives circulation a width and lets its length fall out of
the plan. Nothing then bounds that length, and `evaluate/metrics.py` scored only
the area coefficient — so a long thin spine and a compact hall of the same area
scored identically. Two things are measured here instead:

* **the stub** — how far a corridor overruns its last door. Past its own clear
  width there is no turning room being provided, only corridor leading nowhere.
* **run per room** — metres of circulation for each room it opens onto. A hall
  serving five rooms in six metres and a corridor serving five in fifteen are
  not the same plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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


def _axis(space: Space) -> tuple[int, float, float, float]:
    """(long axis, low, high, width) of a circulation space."""
    minx, miny, maxx, maxy = space.net_polygon.bounds
    if (maxx - minx) >= (maxy - miny):
        return 0, minx, maxx, maxy - miny
    return 1, miny, maxy, maxx - minx


def _served_interval(
    fabric: FabricPlan, space: Space, axis: int, door_module: float
) -> tuple[float, float] | None:
    """The stretch of the corridor's long axis that actually has doors on it.

    A room opens onto the corridor over the run they share; projected onto the
    corridor's own axis that run is an interval, and the union of those
    intervals is the part of the corridor doing any work.
    """
    low = high = None
    for nom, other in fabric.spaces.items():
        if other is space:
            continue
        if fabric.shared_wall_length(space.nom, nom) < door_module:
            continue
        start = max(space.net_polygon.bounds[axis], other.net_polygon.bounds[axis])
        stop = min(
            space.net_polygon.bounds[axis + 2], other.net_polygon.bounds[axis + 2]
        )
        if stop - start <= TOL:
            continue
        low = start if low is None else min(low, start)
        high = stop if high is None else max(high, stop)
    return None if low is None else (low, high)


def circulation_runs(fabric: FabricPlan) -> CirculationReport:
    """Measure every circulation space: what it serves, and what it wastes."""
    door_module = fabric.profile.door_module
    runs: list[Run] = []

    for nom, space in fabric.spaces.items():
        if not space.kind.is_circulation:
            continue
        axis, low, high, width = _axis(space)
        served = sorted(
            other
            for other in fabric.spaces
            if other != nom
            and not fabric.spaces[other].kind.is_circulation
            and fabric.shared_wall_length(nom, other) >= door_module
        )
        interval = _served_interval(fabric, space, axis, door_module)
        if interval is None:
            stub = high - low
        else:
            stub = max(interval[0] - low, high - interval[1], 0.0)
        runs.append(Run(nom, high - low, width, served, stub))

    return CirculationReport(sorted(runs, key=lambda r: r.nom))
