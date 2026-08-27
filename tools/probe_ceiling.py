"""How many rooms can the engine actually place, from a brief nobody calibrated?

    python tools/probe_ceiling.py

The engine's only working reference is `tests/test_search.py`: five rooms and a
spine on 12 x 10 m, with `TARGETS` calibrated by hand to what that envelope and
that exact tree deliver. Its own docstring says so. Every green test downstream
inherits that shape, which is why 313 passing tests do not tell you where the
engine stops.

This probe drives the path the *studio* drives: a round-number programme, a
generous parcel, `fit_brief` to solve the footprint, and the studio's own
`seed_tree`. Measured 2026-08-27:

    rooms  ok/seeds    best    top refusals
        4  crash             fit_footprint: "no footprint under 3351830.7 m2
                             delivers the 64.00 m2 demanded"
        5  6/6       0.814   -
        6  0/6       -       furniture=1033, area=756
        7  0/6       -       furniture=1211, area=588
        8  0/6       -       furniture=1201, area=594
        9  0/6       -       furniture=1089, area=711
       10  0/6       -       furniture=959,  area=841
       11  0/6       -       furniture=1002, area=797
       12  0/6       -       furniture=1063, area=736
       13  0/6       -       furniture=998,  area=801

So the "ceiling 9 cells" recorded in PROGRESS S16-S18 is PATH-DEPENDENT: it was
reached by the search's own moves from a shaped seed, and does not survive the
entry path the studio uses. `furniture` dominates every refusal, and
`max_ratio = 3.0` in `habitability/furniture.py` is an invented number standing
in for the unimplemented ART. 4 daylight-depth rule.

The 4-room crash is a separate bug: the secant in `fit_footprint` diverges by
six orders of magnitude instead of bracketing.

Re-run this whenever a gate, a move or the footprint solver changes. A number
that moves is the finding; the table above is the baseline it moved from.
"""

from __future__ import annotations

import math
import time

from shapely.geometry import Polygon

from planfgen.brief import (
    MA_PROFILE,
    Brief,
    EdgeSpec,
    EdgeType,
    Orientation,
    Parcel,
    Programme,
    RoomSpec,
    RoomType,
    check_feasibility,
)
from planfgen.brief.footprint import fit_brief
from planfgen.partition import BandCut, Cut, Direction, Leaf, SlicingTree
from planfgen.search import RunStats, anneal
from planfgen.topology import ProgrammeGraph, Relation, RelationType

#: A programme that grows F2 -> F3 -> F4 -> F5 -> villa, in round numbers,
#: because round numbers are what a human types. Nothing here is calibrated.
CATALOG: list[tuple[str, str, float, str]] = [
    ("Sejour", "SEJOUR", 30.0, "S"),
    ("Cuisine", "CUISINE", 12.0, "N"),
    ("Ch1", "CHAMBRE_PRINCIPALE", 16.0, "S"),
    ("SDB", "SDB", 6.0, "E"),
    ("Couloir", "COULOIR", 8.0, ""),
    ("Ch2", "CHAMBRE", 13.0, "N"),
    ("WC", "WC", 2.0, "N"),
    ("Ch3", "CHAMBRE", 12.0, "E"),
    ("Cellier", "CELLIER", 5.0, "N"),
    ("Ch4", "CHAMBRE", 12.0, "O"),
    ("Bureau", "BUREAU", 10.0, "E"),
    ("SDB2", "SDB", 5.0, "O"),
    ("Buanderie", "CELLIER", 5.0, "N"),
]

#: How much bigger than the net demand the parcel is. Generous on purpose — the
#: point is to fail for a reason other than not enough site.
SITE_FACTOR = 1.55

#: PROGRESS S15 measured 8 of 8 seeds finding a plan at this aspect and 0 of 12
#: at the 26x12 the parcel's own proportion would give, so it is held fixed here
#: to keep the footprint's proportion from being the variable under test.
ASPECT = 1.25


def _chain(noms: list[str]):
    node = Leaf(noms[-1])
    for nom in reversed(noms[:-1]):
        node = Cut(Direction.H, False, (Leaf(nom), node))
    return node


def seed_tree(programme: Programme) -> SlicingTree:
    """A spine with the rooms hung off it — the studio's own heuristic.

    Copied from `studio/app.py` deliberately. If a better tree lifts the
    ceiling, the finding is that seeding is unsolved, not that the search is
    weak, and that is worth knowing separately.
    """
    rooms = [r.nom for r in programme.rooms if not r.kind.is_circulation]
    half = max(1, len(rooms) // 2)
    return SlicingTree(
        BandCut(Direction.V, (_chain(rooms[:half]), _chain(rooms[half:])))
    )


def build(n: int) -> tuple[Brief, SlicingTree, ProgrammeGraph]:
    """An uncalibrated brief for the first `n` rooms of the catalog."""
    programme = Programme(
        [
            RoomSpec(
                nom=nom,
                kind=RoomType[kind],
                surface_utile=area,
                couleur="#888888",
                orientation_pref=Orientation[pref] if pref else None,
            )
            for nom, kind, area, pref in CATALOG[:n]
        ]
    )
    side = math.sqrt(programme.total_utile * SITE_FACTOR)
    parcel = Parcel(
        outline=Polygon([(0, 0), (side, 0), (side, side * 0.8), (0, side * 0.8)]),
        edges=[
            EdgeSpec(0, EdgeType.STREET),
            EdgeSpec(1, EdgeType.GARDEN),
            EdgeSpec(2, EdgeType.GARDEN),
            EdgeSpec(3, EdgeType.GARDEN),
        ],
        north=0.0,
        entry_edge=0,
    )
    brief = Brief(programme, parcel, MA_PROFILE, check_feasibility(programme, parcel, MA_PROFILE))
    tree = seed_tree(programme)
    graph = ProgrammeGraph(
        [
            Relation("Couloir", room.nom, RelationType.CONNECTED, 2.0)
            for room in programme.rooms
            if not room.kind.is_circulation
        ]
    )
    return brief, tree, graph


def probe(n: int, seeds: int = 6, iterations: int = 300) -> str:
    """One row of the table. Six seeds because one proves nothing.

    PROGRESS S18 records a metric test that flipped merely because two new moves
    changed the draw order — the search is stochastic and a single run samples
    one corner of the space.
    """
    brief, tree, graph = build(n)
    try:
        brief = fit_brief(brief, tree, aspect=ASPECT)
    except Exception as exc:
        return f"{n:>5}  {'crash':>9}  {'-':>7}  {'-':>6}  {type(exc).__name__}: {exc}"

    hits, best, refused = 0, 0.0, {}
    started = time.time()
    for seed in range(seeds):
        stats = RunStats()
        found = anneal(brief, tree, iterations, seed=seed, graph=graph, stats=stats)
        if found:
            hits += 1
            best = max(best, found[0].scores.globale)
        else:
            for gate, count in stats.rejected_by.items():
                refused[gate] = refused.get(gate, 0) + count
    elapsed = time.time() - started

    top = ", ".join(
        f"{gate}={count}"
        for gate, count in sorted(refused.items(), key=lambda kv: -kv[1])[:3]
    )
    score = f"{best:.3f}" if hits else "-"
    return f"{n:>5}  {f'{hits}/{seeds}':>9}  {score:>7}  {elapsed:>6.1f}  {top or '-'}"


def main() -> None:
    print(f"{'rooms':>5}  {'ok/seeds':>9}  {'best':>7}  {'sec':>6}  top refusals")
    for n in range(4, len(CATALOG) + 1):
        print(probe(n), flush=True)


if __name__ == "__main__":
    main()
