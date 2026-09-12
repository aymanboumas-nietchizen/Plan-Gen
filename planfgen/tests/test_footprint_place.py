"""S15 — where the building stands, and letting the search argue about it.

S14 solved how big a footprint is. Its position was a placeholder: centred, then
shoved against the entry edge because a building floating in its parcel has no
street frontage and nothing can reach it. This file is the rule that replaced
the shove, and the two moves that let the annealer disagree with it.

The measurement that shaped the moves is in `test_footprint_moves_wait_for_a_
valid_plan`. Proposing them from iteration zero made the search *worse* — some
seeds went from finding a plan to finding none — because while nothing has
passed the gates there is nothing to refine, and every metre the building moves
is a tree move not taken.
"""

from __future__ import annotations

import random
import sys

import pytest
from shapely.geometry import Polygon

import planfgen.search.anneal  # noqa: F401  - for sys.modules, see ANNEAL
from planfgen.brief import (
    MA_PROFILE,
    Brief,
    EdgeSpec,
    EdgeType,
    Footprint,
    Parcel,
    check_feasibility,
    delivered,
    fit_brief,
    place_footprint,
    sized_demand,
)
from planfgen.search import anneal
from planfgen.search.moves import (
    BRIEF_MOVES,
    mutate_brief,
    shape_footprint,
    slide_footprint,
)
from planfgen.tests.test_footprint import DEMAND, programme, tree
from planfgen.topology import ProgrammeGraph, Relation, RelationType as R

#: The module, not the function. `planfgen.search` re-exports `anneal` as a
#: name, so `import planfgen.search.anneal as ANNEAL` binds the function that
#: shadows the module and its constants are then unreachable.
ANNEAL = sys.modules["planfgen.search.anneal"]

P = MA_PROFILE

#: Reused so the placement tests all read against the same building.
SIZE = Footprint(0.0, 0.0, 10.0, 8.0)


def site(
    w: float,
    h: float,
    kinds: tuple[EdgeType, EdgeType, EdgeType, EdgeType],
    setbacks: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
    entry: int = 0,
) -> Parcel:
    """A rectangle whose edges run bottom, right, top, left."""
    return Parcel(
        outline=Polygon([(0, 0), (w, 0), (w, h), (0, h)]),
        edges=[
            EdgeSpec(i, kind, back)
            for i, (kind, back) in enumerate(zip(kinds, setbacks))
        ],
        north=0.0,
        entry_edge=entry,
    )


STREET, MITOYEN, COURT, GARDEN = (
    EdgeType.STREET,
    EdgeType.MITOYEN,
    EdgeType.COURT,
    EdgeType.GARDEN,
)


def graph() -> ProgrammeGraph:
    return ProgrammeGraph(
        [
            Relation("Couloir", nom, R.CONNECTED, 1.5)
            for nom in ("Sejour", "Cuisine", "Ch1", "Ch2", "SDB")
        ]
    )


def brief_on(parcel: Parcel) -> Brief:
    prog = programme()
    return Brief(prog, parcel, P, check_feasibility(prog, parcel, P))


# --- the sides of a parcel --------------------------------------------------


def test_every_edge_of_a_rectangle_lands_on_a_side():
    parcel = site(20.0, 12.0, (STREET, MITOYEN, COURT, GARDEN))
    assert [parcel.side_of(i) for i in range(4)] == [
        "bottom",
        "right",
        "top",
        "left",
    ]


def test_setbacks_shrink_what_may_be_built_on():
    parcel = site(20.0, 12.0, (STREET, MITOYEN, COURT, GARDEN), (3.0, 0.0, 1.0, 2.0))
    assert parcel.buildable_bounds() == pytest.approx((2.0, 3.0, 20.0, 11.0))


def test_setbacks_that_leave_nothing_say_so():
    parcel = site(8.0, 6.0, (STREET, GARDEN, COURT, GARDEN), (3.0, 0.0, 3.5, 0.0))
    with pytest.raises(ValueError, match="leave nothing to build on"):
        parcel.buildable_bounds()


def test_a_setback_cannot_be_negative():
    with pytest.raises(ValueError, match="cannot be negative"):
        EdgeSpec(0, EdgeType.STREET, -1.0)


def test_a_setback_survives_the_json():
    spec = EdgeSpec.from_json({"index": 2, "kind": "RETRAIT", "setback": 4.5})
    assert (spec.index, spec.kind, spec.setback) == (2, EdgeType.RETRAIT, 4.5)
    assert EdgeSpec.from_json({"index": 0, "kind": "STREET"}).setback == 0.0


# --- the placement rule -----------------------------------------------------


def test_a_party_wall_is_built_up_to():
    """That is what makes it a party wall."""
    placed = place_footprint(SIZE, site(20.0, 12.0, (STREET, MITOYEN, COURT, GARDEN)))
    assert placed.x + placed.w == pytest.approx(20.0), "flush right, on the mitoyen"
    assert placed.y == pytest.approx(0.0), "and flush to the entry"


def test_the_entry_decides_when_there_is_no_party_wall():
    placed = place_footprint(SIZE, site(20.0, 12.0, (STREET, GARDEN, COURT, GARDEN)))
    assert placed.y == pytest.approx(0.0), "the entry is the bottom edge"
    assert placed.x == pytest.approx((20.0 - 10.0) / 2), "nothing to align x to"


def test_an_entry_on_the_far_side_pulls_the_building_to_it():
    placed = place_footprint(
        SIZE, site(20.0, 12.0, (COURT, GARDEN, STREET, GARDEN), entry=2)
    )
    assert placed.y + placed.h == pytest.approx(12.0)


def test_a_party_wall_beats_the_entry():
    """Both on the same axis: the boundary wins, and the entry is still on the
    street because the building is deep enough to reach both."""
    placed = place_footprint(
        SIZE, site(20.0, 12.0, (STREET, GARDEN, MITOYEN, GARDEN))
    )
    assert placed.y + placed.h == pytest.approx(12.0), "flush to the party wall"


def test_two_party_walls_take_the_low_side():
    placed = place_footprint(SIZE, site(20.0, 12.0, (STREET, MITOYEN, COURT, MITOYEN)))
    assert placed.x == pytest.approx(0.0)


def test_a_setback_is_respected_even_flush():
    """"Flush" means flush to the buildable limit, not to the boundary."""
    parcel = site(20.0, 12.0, (STREET, MITOYEN, COURT, GARDEN), (2.0, 1.5, 0.0, 0.0))
    placed = place_footprint(SIZE, parcel)
    assert placed.x + placed.w == pytest.approx(20.0 - 1.5)
    assert placed.y == pytest.approx(2.0)
    assert placed.buildable(parcel)


def test_placement_is_centred_with_neither():
    parcel = site(20.0, 12.0, (COURT, GARDEN, COURT, GARDEN), entry=1)
    placed = place_footprint(SIZE, parcel)
    assert placed.y == pytest.approx((12.0 - 8.0) / 2)


def test_fit_brief_places_a_solved_building():
    parcel = site(18.0, 15.0, (STREET, MITOYEN, COURT, GARDEN), (1.0, 0.0, 0.0, 2.0))
    fitted = fit_brief(brief_on(parcel), tree())
    assert fitted.footprint.buildable(parcel)
    assert fitted.footprint.x + fitted.footprint.w == pytest.approx(18.0)
    assert fitted.footprint.y == pytest.approx(1.0)


# --- the moves --------------------------------------------------------------


def roomy() -> Brief:
    """A brief with real freedom: the building covers about half its site."""
    return fit_brief(brief_on(site(16.0, 13.0, (STREET, COURT, COURT, COURT))), tree())


def test_a_slide_stays_inside_what_may_be_built_on():
    brief = roomy()
    rng = random.Random(0)
    walk = brief
    for _ in range(200):
        walk = slide_footprint(walk, rng)
        assert walk.footprint.buildable(walk.parcel)


def test_a_slide_does_not_resize():
    brief = roomy()
    moved = slide_footprint(brief, random.Random(1))
    assert (moved.footprint.w, moved.footprint.h) == (
        brief.footprint.w,
        brief.footprint.h,
    )


def test_a_slide_actually_moves():
    brief = roomy()
    rng = random.Random(2)
    assert any(
        slide_footprint(brief, rng).footprint.x != brief.footprint.x
        for _ in range(20)
    )


def test_a_building_that_fills_its_site_has_nowhere_to_slide():
    tight = fit_brief(brief_on(site(11.7, 9.5, (STREET, COURT, COURT, COURT))), tree())
    rng = random.Random(3)
    for _ in range(20):
        assert slide_footprint(tight, rng).footprint.within(tight.parcel)


def test_a_reshape_keeps_the_rooms_exactly_as_asked():
    """Constant *delivered* area, not constant footprint area — a longer, thinner
    building spends more on facade, so keeping the gross would shrink the rooms."""
    brief = roomy()
    rng = random.Random(4)
    reshaped = 0
    for _ in range(12):
        moved = shape_footprint(brief, rng, tree())
        if moved.footprint.aspect == pytest.approx(brief.footprint.aspect):
            continue
        reshaped += 1
        got = delivered(
            moved.footprint, moved.programme, moved.parcel, P, tree()
        )
        assert got == pytest.approx(sized_demand(moved.programme, tree()), abs=1e-9)
        assert got == pytest.approx(DEMAND, abs=1e-9)
        assert moved.footprint.buildable(moved.parcel)
    assert reshaped, "the fixture has room to reshape; something is not moving"


def test_a_reshape_that_will_not_fit_keeps_the_building_it_had():
    tight = fit_brief(brief_on(site(11.7, 9.5, (STREET, COURT, COURT, COURT))), tree())
    rng = random.Random(5)
    for _ in range(20):
        moved = shape_footprint(tight, rng, tree())
        assert moved.footprint.buildable(moved.parcel)


def test_the_moves_leave_a_brief_without_a_footprint_alone():
    """Such a brief builds on its whole parcel. Quietly giving it a smaller
    building would answer a different question from the one that was asked."""
    raw = brief_on(site(16.0, 13.0, (STREET, COURT, COURT, COURT)))
    assert raw.footprint is None
    rng = random.Random(6)
    assert slide_footprint(raw, rng) is raw
    assert shape_footprint(raw, rng, tree()) is raw
    assert mutate_brief(raw, tree(), rng) is raw


def test_every_brief_move_returns_a_brief():
    brief = roomy()
    rng = random.Random(7)
    for move in BRIEF_MOVES:
        out = move(brief, rng, tree()) if move is shape_footprint else move(brief, rng)
        assert isinstance(out, Brief)
        assert out.footprint.buildable(out.parcel)


# --- and what the search does with them --------------------------------------


def test_the_search_moves_the_building():
    """Across seeds, not on any one of them — a run whose winner happens to be
    an unmoved building is a perfectly good run."""
    brief = roomy()
    winners = [
        anneal(brief, tree(), 400, seed=s, graph=graph())[0].brief.footprint
        for s in range(1, 7)
    ]
    assert all(fp.buildable(brief.parcel) for fp in winners)
    assert any(fp != brief.footprint for fp in winners), "the building never moved"


def test_what_the_search_returns_says_what_it_was_built_to():
    """The footprint is a search variable, so the brief handed in is not
    necessarily the brief the winning plan was built to."""
    best = anneal(roomy(), tree(), 300, seed=1, graph=graph())
    assert best[0].brief is best[0].plan.brief


def test_footprint_moves_wait_for_a_valid_plan():
    """Until something passes the gates there is nothing to refine.

    Proposing them from iteration zero measured strictly worse: on a 20 x 16 m
    parcel two of eight seeds went from finding a plan to finding none, because
    a fifth of the budget went on moving a building whose *tree* was what the
    gates were refusing.
    """
    hopeless = fit_brief(
        brief_on(site(9.0, 7.2, (STREET, COURT, COURT, COURT))), tree()
    )
    assert hopeless.footprint is not None, "movable, so the guard is what stops it"

    calls = []
    real = ANNEAL.mutate_brief
    ANNEAL.mutate_brief = lambda *a, **k: (calls.append(1), real(*a, **k))[1]
    try:
        assert anneal(hopeless, tree(), 300, seed=1, graph=graph()) == []
    finally:
        ANNEAL.mutate_brief = real
    assert not calls, f"{len(calls)} footprint moves proposed with nothing to refine"


def test_moving_the_building_earns_its_keep():
    """Measured, because it costs: a reshape re-solves the footprint.

    Six seeds on the roomy fixture, 400 iterations. The sweep behind the default
    of 0.20 is in PROGRESS.md; this only guards the sign of the effect.
    """
    brief = roomy()
    was = ANNEAL.P_FOOTPRINT

    def mean(p: float) -> float:
        ANNEAL.P_FOOTPRINT = p
        runs = [anneal(brief, tree(), 400, seed=s, graph=graph()) for s in range(1, 7)]
        return sum(r[0].scores.globale if r else 0.0 for r in runs) / len(runs)

    try:
        still, moving = mean(0.0), mean(was)
    finally:
        ANNEAL.P_FOOTPRINT = was
    assert moving > still, f"{moving:.4f} against {still:.4f}"

def test_a_tree_restart_keeps_the_building_it_walked_to():
    """The restart is on the tree, not on the brief.

    Its job is to stop an unbounded walk wandering into ever stranger trees.
    Resetting the footprint with it meant the building could never travel from
    the proportion it was fitted at to a better one, because a third of the
    drift threw the journey away.
    """
    brief = roomy()
    winners = [
        anneal(brief, tree(), 400, seed=s, graph=graph())[0].brief.footprint
        for s in range(1, 7)
    ]
    assert any(fp != brief.footprint for fp in winners)


def test_an_elongated_parcel_needs_its_aspect_choosing():
    """A known limit, pinned so it is not rediscovered by accident.

    `fit_footprint` defaults to the parcel's own proportion, which on a long
    thin plot fits a long thin building — and a building 15 m by 7 m gives its
    rooms the shape of strips that no rearrangement can furnish. Measured on a
    26 x 12 m parcel: 0 of 12 seeds find a plan at the default, and 8 of 8 at an
    aspect of 1.25, which is the *same building* the search settles on when the
    parcel happens to be squarer.

    Letting the annealer reshape before it has anything valid does rescue some
    of it — see `P_FOOTPRINT_COLD` — but costs about a tenth of the score on
    ordinary parcels. Choosing the aspect properly wants the reference plans of
    S18; until then it is the caller's to pass.
    """
    long_thin = brief_on(site(26.0, 12.0, (STREET, COURT, COURT, COURT)))

    default = fit_brief(long_thin, tree())
    assert default.footprint.aspect > 2.0, "the parcel's own proportion"
    assert not any(
        anneal(default, tree(), 250, seed=s, graph=graph()) for s in range(1, 4)
    )

    chosen = fit_brief(long_thin, tree(), aspect=1.25)
    assert chosen.footprint.buildable(chosen.parcel)
    assert all(
        anneal(chosen, tree(), 250, seed=s, graph=graph()) for s in range(1, 4)
    )

