"""How many rooms can the engine actually place, from a brief nobody calibrated?

    python tools/probe_ceiling.py

The engine's only working reference is `tests/test_search.py`: five rooms and a
spine on 12 x 10 m, with `TARGETS` calibrated by hand to what that envelope and
that exact tree deliver. Its own docstring says so. Every green test downstream
inherits that shape, which is why 313 passing tests do not tell you where the
engine stops.

This probe drives the path the *studio* drives: a round-number programme, a
generous parcel, `fit_brief` to solve the footprint, and the studio's own
`seed_tree`. Measured 2026-08-28, and 5 through 13 unchanged from 2026-08-27:

    rooms  ok/seeds    best    top refusals
        4  6/6       0.843   -       (was a crash; see below)
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
entry path the studio uses. `furniture` dominates every refusal. Note that
`max_ratio = 3.0` in `habitability/furniture.py` is MEASURED, not invented — its
docstring carries the sweep — but it is the project's own figure standing in for
the unimplemented ART. 4 daylight-depth rule.

THE 4-ROOM CRASH WAS AN INVALID INPUT, NOT A DIVERGING SECANT. `CATALOG[:4]`
has no circulation room — `Couloir` is the fifth entry — and `seed_tree` built a
`BandCut` anyway, so `realise` raised "more bands than spare circulation rooms"
at every area. `fit_footprint`'s bracket read that as "the footprint is too
small", grew it by 1.3 forty times and reported 1.45 x 64 x 1.3^40 = 3351830.7
as a site failure. Fixed 2026-08-28 on both sides: the tree refuses an
unnameable band before any geometry (`UnrealisableTree`), the bracket grows only for the one
failure a larger footprint can fix (`EnvelopeTooTight`), and `seed_tree` here
builds a band only when there is a name for it. THE CEILING DID NOT MOVE: 5
through 13 are identical, to the refusal count, before and after.

The 4-room row's `best` is not comparable with the rows below it. A programme
with no circulation room has no hub to relate anything to, so its graph is empty
and `adjacences` returns 1.0 by vacuity — 0.843 is inflated by that term.

THE CEILING IS STRUCTURAL, NOT REGULATORY. Run across all three profiles
2026-08-27, re-run 2026-08-28 — the placeholder `MA_PROFILE`, plus the two
sourced ones that the studio has never used:

    profile      corridor_clear  daylight  4 rooms   5 rooms   6-13 rooms
    placeholder      1.20         0.1250   6/6 0.843  6/6 0.814   all 0/6
    economique       0.80         0.1000   6/6 0.843  6/6 0.831   all 0/6
    casablanca       0.90         0.1667   6/6 0.843  6/6 0.831   all 0/6

Identical ceiling, `furniture` dominant throughout. So the placeholder
numbers are not what caps the engine, and no amount of sourcing
regulation will lift it. Two things the sweep also shows:

  - the sourced profiles trade one refusal for another rather than reducing
    them: a narrower corridor gives rooms more area (`area` 756 -> 677 at six
    rooms) and worse proportions (`furniture` 1033 -> 1116). Net zero.
  - economique and casablanca are nearly identical DESPITE disagreeing on SDB
    minimum (1.30 vs 3.00 m2), SEJOUR (12 vs 14) and daylight ratio (0.10 vs
    0.167). The minima are not binding: this catalog's round numbers sit well
    above all of them, so they never fire. A probe with a programme sized near
    the minima would be a different measurement, and has not been run.

Re-run this whenever a gate, a move or the footprint solver changes. A number
that moves is the finding; the tables above are the baseline it moved from.
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
from planfgen.brief.regulation import PROFILES, RegulationProfile
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

    ONE DIVERGENCE, added 2026-08-28: the spine is a band only when the
    programme has a circulation room to name it. `CATALOG[:4]` has none — `Couloir` is the fifth
    entry — and a band nobody can name is a tree no envelope can realise, so the
    studio's unconditional `BandCut` made the four-room row an invalid input
    rather than a measurement. `studio/app.py` has the same hole and guards only
    `len(rooms) < 2`; that is a bug for `planfgen-product`, not one to reach in
    and fix from here.
    """
    rooms = [r.nom for r in programme.rooms if not r.kind.is_circulation]
    half = max(1, len(rooms) // 2)
    halves = (_chain(rooms[:half]), _chain(rooms[half:]))
    if programme.circulation_rooms:
        return SlicingTree(BandCut(Direction.V, halves))
    return SlicingTree(Cut(Direction.V, False, halves))


def build(n: int, profile: RegulationProfile = MA_PROFILE) -> tuple[Brief, SlicingTree, ProgrammeGraph]:
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
    brief = Brief(programme, parcel, profile, check_feasibility(programme, parcel, profile))
    tree = seed_tree(programme)
    # Everything connects to the corridor — when there is one. Naming `Couloir`
    # unconditionally scored the four-room row 0.0 on adjacency for relations to
    # a room that is not in its programme. A programme with no circulation room
    # states no adjacency requirement, so it gets none, and `adjacences` returns
    # 1.0 by vacuity: the four-room `best` is therefore NOT comparable with the
    # rows below it on that term.
    hub = next((room.nom for room in programme.circulation_rooms), None)
    graph = ProgrammeGraph(
        [
            Relation(hub, room.nom, RelationType.CONNECTED, 2.0)
            for room in programme.rooms
            if not room.kind.is_circulation
        ]
        if hub
        else []
    )
    return brief, tree, graph


def probe(n: int, profile: RegulationProfile = MA_PROFILE, seeds: int = 6, iterations: int = 300) -> str:
    """One row of the table. Six seeds because one proves nothing.

    PROGRESS S18 records a metric test that flipped merely because two new moves
    changed the draw order — the search is stochastic and a single run samples
    one corner of the space.
    """
    brief, tree, graph = build(n, profile)
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
    """Every named profile, because the engine has only ever been run on one.

    `MA_PROFILE` is the unsourced placeholder and is what `studio/app.py` uses
    at every call site; `MA_ECONOMIQUE` (decret 2-64-445) and `MA_CASABLANCA`
    (arrete municipal) are the sourced ones and are used nowhere outside tests.
    They disagree — corridor_clear is 1.20 / 0.80 / 0.90 and the minima differ
    room by room — so the ceiling is not one number, it is one per profile.
    """
    for name, profile in PROFILES.items():
        print(f"\n=== {name} ===")
        print(f"  corridor_clear={profile.corridor_clear:.2f}  "
              f"daylight_ratio={profile.daylight_ratio:.4f}")
        print(f"{'rooms':>5}  {'ok/seeds':>9}  {'best':>7}  {'sec':>6}  top refusals")
        for n in range(4, len(CATALOG) + 1):
            print(probe(n, profile), flush=True)


if __name__ == "__main__":
    main()
