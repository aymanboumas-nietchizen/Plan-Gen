"""Soft scores — the judgement calls, and only those.

There is no `couverture`. v1 shipped it and it returned exactly 1.0 on all forty
seeds: one distinct value, a quarter of the weight, and no signal whatsoever.
A number that cannot vary is not a metric, and the variance test in
`test_search.py` exists to keep that from happening again.

`compacite` is kept but rescaled. v1's spanned 0.9435 to 1.0000 across its whole
search — 1.4 points of signal out of 25 — because it measured the envelope,
which barely moves. This one measures room shape, which moves a great deal.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from planfgen.brief.plan import Brief
from planfgen.brief.programme import Orientation
from planfgen.evaluate.constraints import fabric_of
from planfgen.topology.relations import ProgrammeGraph, RelationType

#: Weights of the four soft scores. They sum to 1.
W_ADJACENCES = 0.45
W_ORIENTATION = 0.20
W_CIRCULATION = 0.20
W_COMPACITE = 0.15

#: Circulation is free up to this coefficient and worthless above the next one.
CIRC_FREE = 0.10
CIRC_SPAN = 0.15

#: The aspect ratio a room is measured against. This is deliberately NOT the
#: 2.5 the aspect gate enforces. Scoring `min(1, 2.5 / ratio)` would saturate at
#: exactly the threshold the gate already guarantees, so every surviving plan
#: would score 1.0 — measured, and it did: one distinct value over fifty runs.
#: That is precisely how v1 shipped `couverture`. A square scores 1.0 and the
#: score falls off from there, so the number has somewhere to move.
SQUARE = 1.0

#: How many door-capable steps still count as "near".
NEAR_STEPS = 2


@dataclass(frozen=True)
class Scores:
    """Four soft scores and their weighted sum.

    `globale` rather than `global`, which is a Python keyword — and French, in
    keeping with the rest of the domain vocabulary.
    """

    adjacences: float
    orientation: float
    circulation: float
    compacite: float
    globale: float
    details: dict = field(default_factory=dict)

    def as_dict(self) -> dict[str, float]:
        return {
            "adjacences": self.adjacences,
            "orientation": self.orientation,
            "circulation": self.circulation,
            "compacite": self.compacite,
            "globale": self.globale,
        }


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def adjacences(plan, brief: Brief, graph: ProgrammeGraph) -> tuple[float, dict]:
    """Satisfied relation weight over total relation weight.

    Each relation type is judged by what it actually demanded: CONNECTED wants a
    run long enough for a door, ADJACENT only wants contact, SEPARATED wants
    none, and NEAR wants a short walk. Measuring all four as "are they close"
    is what let v1 report 7 of 9 adjacencies on a plan where only 5 could take
    a door.
    """
    if not graph.relations:
        return 1.0, {}

    fabric = fabric_of(plan, brief)
    spaces = fabric.spaces
    satisfied: dict[str, bool] = {}
    total = got = 0.0

    for relation in graph.relations:
        a, b = relation.pair
        total += relation.weight
        if a not in spaces or b not in spaces:
            satisfied[f"{a}~{b}"] = False
            continue

        run = fabric.shared_wall_length(a, b)
        if relation.kind is RelationType.CONNECTED:
            ok = run >= brief.profile.door_module
        elif relation.kind is RelationType.ADJACENT:
            ok = run > 0.0
        elif relation.kind is RelationType.SEPARATED:
            ok = run == 0.0
        else:
            ok = _within(fabric, a, b, NEAR_STEPS)

        satisfied[f"{a}~{b}"] = ok
        if ok:
            got += relation.weight

    return got / total, satisfied


def _within(fabric, start: str, target: str, steps: int) -> bool:
    """True if `target` is within `steps` door-capable moves of `start`."""
    adjacency = fabric.adjacency_graph()
    frontier, seen = {start}, {start}
    for _ in range(steps):
        frontier = {n for f in frontier for n in adjacency[f]} - seen
        if target in frontier:
            return True
        seen |= frontier
    return False


def orientation(plan, brief: Brief) -> tuple[float, dict]:
    """Fraction of rooms that got the aspect they asked for.

    A room's orientation is the parcel edge it presents the most frontage to.
    Rooms with no preference are not counted either way — a score should not be
    diluted by rooms that had no opinion.
    """
    wanted = {
        room.nom: room.orientation_pref
        for room in brief.programme.rooms
        if room.orientation_pref is not None
    }
    if not wanted:
        return 1.0, {}

    fabric = fabric_of(plan, brief)
    faced = facings(fabric)
    met = {nom: faced.get(nom) is pref for nom, pref in wanted.items()}
    return sum(met.values()) / len(met), met


def facings(fabric) -> dict[str, Orientation | None]:
    """The compass sector each space presents most of its frontage to."""
    parcel = fabric.parcel
    edges = range(len(parcel.outline.exterior.coords) - 1)
    out: dict[str, Orientation | None] = {}
    for nom, space in fabric.spaces.items():
        runs = [(fabric.edge_length_on(space, e), e) for e in edges]
        best_run, best_edge = max(runs, default=(0.0, None))
        out[nom] = parcel.orientation_of(best_edge) if best_run > 0 else None
    return out


def circulation(plan, brief: Brief) -> float:
    """Full marks up to a 10% circulation coefficient, nothing by 25%.

    The coefficient is a result, never an input — ARCHITECTURE section 4. This
    scores it rather than letting the programme ask for it.
    """
    coefficient = plan.circulation_coefficient(brief.profile)
    return 1.0 - _clamp((coefficient - CIRC_FREE) / CIRC_SPAN)


def compacite(plan, brief: Brief) -> float:
    """Mean room compactness — how square the rooms are, on net dimensions.

    A square scores 1.0 and a 2.5:1 room, which is the worst the aspect gate
    lets through, scores 0.4. See `SQUARE` for why the reference is not 2.5.
    Bands are left out: a corridor is meant to be long and thin.
    """
    profile = brief.profile
    rooms = [c for c in plan.cells if not c.is_band]
    if not rooms:
        return 1.0
    scores = []
    for cell in rooms:
        net_w, net_h = cell.net_dims(profile)
        if net_w <= 0 or net_h <= 0:
            scores.append(0.0)
            continue
        ratio = max(net_w, net_h) / min(net_w, net_h)
        scores.append(min(1.0, SQUARE / ratio))
    return sum(scores) / len(scores)


def score(plan, brief: Brief, graph: ProgrammeGraph | None = None) -> Scores:
    """Every soft score, and their weighted sum.

    Without a relation graph there is nothing to satisfy, so `adjacences` is
    1.0 — vacuously true rather than silently zero.
    """
    graph = graph if graph is not None else ProgrammeGraph()
    adj, adj_detail = adjacences(plan, brief, graph)
    orient, orient_detail = orientation(plan, brief)
    circ = circulation(plan, brief)
    comp = compacite(plan, brief)

    return Scores(
        adjacences=adj,
        orientation=orient,
        circulation=circ,
        compacite=comp,
        globale=(
            W_ADJACENCES * adj
            + W_ORIENTATION * orient
            + W_CIRCULATION * circ
            + W_COMPACITE * comp
        ),
        details={
            "adjacences": adj_detail,
            "orientation": orient_detail,
            "circulation_coefficient": plan.circulation_coefficient(brief.profile),
        },
    )
