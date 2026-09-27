"""Real programmes through the studio's own pipeline, with and without fit_brief.

    python tools/probe_programmes.py            # all profiles
    python tools/probe_programmes.py casablanca # one

`probe_ceiling.py` grows a synthetic catalogue one room at a time. This runs
what an architect in the agency would actually type — an F2 to an F4, sized the
way Moroccan flats are sized, on lots the size they come in — through exactly
what `studio/app.py` does: `seed_tree`, then `anneal` on the brief as built.

Column `studio` is the studio as it stands, building on the whole parcel.
Column `fit` sends the same brief through `fit_brief` first. The difference
between the two columns is the argument for wiring the solver into the studio.

The `-WC` and `-Entree` rows are the same programmes with the separate WC folded
into the SDB and the ENTREE line removed, which isolates the two programme lines
the engine cannot yet place (see PROGRESS.md S23).
"""

from __future__ import annotations

import sys
from collections import Counter

from shapely.geometry import Polygon

from planfgen.brief import (
    Brief, EdgeSpec, EdgeType, Orientation, Parcel, Programme, RoomSpec, RoomType,
    check_feasibility,
)
from planfgen.brief.footprint import fit_brief
from planfgen.brief.regulation import PROFILES
from planfgen.search import RunStats, anneal
from planfgen.studio.seed import seed_tree
from planfgen.topology import ProgrammeGraph, Relation, RelationType

SEEDS = (1, 2, 3, 4)
ITERATIONS = 300

#: Lot edges as the studio defaults them: street south, party walls east and west.
EDGES = ("STREET", "MITOYEN", "COURT", "MITOYEN")

#: (nom, kind, m2, orientation). Areas are typical agency figures, not calibrated
#: to any parcel — which is the point.
PROGRAMMES: dict[str, list[tuple[str, str, float, str | None]]] = {
    "F2 50": [
        ("Sejour", "SEJOUR", 18, "S"), ("Cuisine", "CUISINE", 7, "N"),
        ("Ch1", "CHAMBRE_PRINCIPALE", 12, "S"), ("SDB", "SDB", 4, None),
        ("Couloir", "COULOIR", 5, None),
    ],
    "F3 75": [
        ("Sejour", "SEJOUR", 24, "S"), ("Cuisine", "CUISINE", 9, "N"),
        ("Ch1", "CHAMBRE_PRINCIPALE", 13, "S"), ("Ch2", "CHAMBRE", 11, "E"),
        ("SDB", "SDB", 5, None), ("WC", "WC", 2, None),
        ("Couloir", "COULOIR", 6, None),
    ],
    "F4 110": [
        ("Entree", "ENTREE", 6, None), ("Sejour", "SEJOUR", 30, "S"),
        ("Cuisine", "CUISINE", 11, "N"), ("Ch1", "CHAMBRE_PRINCIPALE", 14, "S"),
        ("Ch2", "CHAMBRE", 12, "E"), ("Ch3", "CHAMBRE", 11, "O"),
        ("SDB", "SDB", 5, None), ("WC", "WC", 2, None),
        ("Couloir", "COULOIR", 9, None),
    ],
}

#: (programme, lot width, lot depth).
CASES = [("F2 50", 8, 8), ("F3 75", 9, 11), ("F4 110", 11, 13)]


def without_wc_and_entree(rooms):
    """The WC folded into the SDB, and no ENTREE line."""
    wc = sum(a for n, k, a, o in rooms if k == "WC")
    out = [r for r in rooms if r[1] not in ("WC", "ENTREE")]
    return [(n, k, a + wc, o) if k == "SDB" else (n, k, a, o) for n, k, a, o in out]


def relations(rooms) -> ProgrammeGraph:
    """What an architect would draw for a flat: night rooms off the corridor."""
    noms = {n: k for n, k, _, _ in rooms}
    hub = "Couloir"
    rel = [
        Relation(hub, n, RelationType.CONNECTED, 2.0)
        for n, k in noms.items()
        if k in ("CHAMBRE", "CHAMBRE_PRINCIPALE", "SDB", "WC")
    ]
    if "Entree" in noms:
        rel += [Relation("Entree", "Sejour", RelationType.CONNECTED, 2.0),
                Relation("Entree", hub, RelationType.CONNECTED, 2.0)]
    else:
        rel.append(Relation(hub, "Sejour", RelationType.CONNECTED, 2.0))
    rel.append(Relation("Sejour", "Cuisine", RelationType.CONNECTED, 1.5))
    rel.append(Relation("Cuisine", "SDB", RelationType.ADJACENT, 1.0))
    rel.append(Relation("SDB", "Sejour", RelationType.SEPARATED, 1.0))
    return ProgrammeGraph(rel)


def brief_for(rooms, width: float, depth: float, profile) -> Brief:
    programme = Programme([
        RoomSpec(nom=n, kind=RoomType[k], surface_utile=float(a), couleur="#888888",
                 orientation_pref=Orientation[o] if o else None)
        for n, k, a, o in rooms
    ])
    parcel = Parcel(
        outline=Polygon([(0, 0), (width, 0), (width, depth), (0, depth)]),
        edges=[EdgeSpec(i, EdgeType[e]) for i, e in enumerate(EDGES)],
        north=0.0,
        entry_edge=0,
    )
    return Brief(programme, parcel, profile, check_feasibility(programme, parcel, profile))


def probe(rooms, width: float, depth: float, profile, fit: bool) -> str:
    brief = brief_for(rooms, width, depth, profile)
    if not brief.budget.ok:
        return f"infeasible ({brief.budget.deficit:.1f} m2 short)"
    tree = seed_tree(brief.programme)
    if fit:
        brief = fit_brief(brief, tree)
    graph = relations(rooms)
    found, best, refused = 0, 0.0, Counter()
    for seed in SEEDS:
        stats = RunStats()
        result = anneal(brief, tree, ITERATIONS, seed=seed, graph=graph, stats=stats)
        refused.update(stats.rejected_by)
        if result:
            found += 1
            best = max(best, result[0].scores.globale)
    top = refused.most_common(1)
    why = f"{top[0][0]}" if top and not found else ""
    return f"{found}/{len(SEEDS)} {best:.3f} {why}".strip()


def main() -> None:
    names = sys.argv[1:] or list(PROFILES)
    for name in names:
        profile = PROFILES[name]
        print(f"\n=== {name} ===")
        print(f"{'programme':18} {'lot':7} {'studio':22} {'fit':22}")
        for programme, width, depth in CASES:
            for label, rooms in (
                (programme, PROGRAMMES[programme]),
                (f"{programme} -WC-Entree", without_wc_and_entree(PROGRAMMES[programme])),
            ):
                cells = [probe(rooms, width, depth, profile, fit) for fit in (False, True)]
                print(f"{label:18} {width}x{depth:<5} {cells[0]:22} {cells[1]:22}", flush=True)


if __name__ == "__main__":
    main()
