"""S14 — the footprint, and whether a brief can now be handed over uncalibrated.

Every fixture in this repo before today carried *calibrated* room areas: numbers
like 32.13 and 18.69, arrived at by realising the tree, measuring what came out,
rescaling the programme and going round again until the area gate stopped
complaining. `test_search.py` says so in its own docstring. That loop is the
reason the engine was a demo rather than a tool — no architect writes a
programme that way.

`test_round_numbers_become_buildable` is the test this session exists for: the
same flat written the way a brief is actually written, in round numbers, failing
the area gate as it stands and passing it after one call.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from shapely.geometry import Polygon

import planfgen.brief.footprint as FP
from planfgen.brief import (
    MA_PROFILE,
    Brief,
    EdgeSpec,
    EdgeType,
    Footprint,
    InfeasibleBrief,
    Orientation,
    Parcel,
    Programme,
    RoomSpec,
    RoomType,
    check_feasibility,
    delivered,
    fit_brief,
    fit_footprint,
    fit_programme,
    scale_for,
    sized_demand,
)
from planfgen.fabric.graph import BOUND_TOL
from planfgen.evaluate import (
    AREA_GATE,
    AREA_TOLERANCE,
    COVERAGE_GATE,
    GATES,
    REACHABLE_GATE,
    facings,
)
from planfgen.partition import BandCut, Cut, Direction, Leaf, SlicingTree
from planfgen.search import envelope_of, grid_for

P = MA_PROFILE
O = Orientation

#: Round numbers — what someone writes down, not what a tree happens to deliver.
SPEC = [
    ("Sejour", RoomType.SEJOUR, 30.0, O.S),
    ("Cuisine", RoomType.CUISINE, 14.0, O.N),
    ("Ch1", RoomType.CHAMBRE_PRINCIPALE, 16.0, O.N),
    ("Ch2", RoomType.CHAMBRE, 12.0, O.S),
    ("SDB", RoomType.SDB, 8.0, O.E),
    ("Couloir", RoomType.COULOIR, 7.0, None),
]

DEMAND = 80.0  # the five leaves; the Couloir names the band and is not one


def programme() -> Programme:
    return Programme(
        [
            RoomSpec(nom, kind, area, "#888888", orientation_pref=pref)
            for nom, kind, area, pref in SPEC
        ]
    )


def parcel(w: float, h: float) -> Parcel:
    return Parcel(
        outline=Polygon([(0, 0), (w, 0), (w, h), (0, h)]),
        edges=[
            EdgeSpec(0, EdgeType.STREET),
            EdgeSpec(1, EdgeType.MITOYEN),
            EdgeSpec(2, EdgeType.COURT),
            EdgeSpec(3, EdgeType.MITOYEN),
        ],
        north=0.0,
        entry_edge=0,
    )


def tree() -> SlicingTree:
    """A spine with three rooms one side and two the other."""

    def chain(direction: Direction, noms: list[str]):
        node = Leaf(noms[-1])
        for nom in reversed(noms[:-1]):
            node = Cut(direction, False, (Leaf(nom), node))
        return node

    return SlicingTree(
        BandCut(
            Direction.V,
            (
                chain(Direction.H, ["Sejour", "Cuisine", "Ch1"]),
                chain(Direction.H, ["Ch2", "SDB"]),
            ),
        )
    )


def brief_on(w: float, h: float) -> Brief:
    prog, site = programme(), parcel(w, h)
    return Brief(prog, site, P, check_feasibility(prog, site, P))


# --- what a footprint is ----------------------------------------------------


def test_the_demand_is_the_leaves_not_the_programme():
    """A circulation room naming a band is not a leaf, so it demands nothing."""
    prog = programme()
    assert sized_demand(prog, tree()) == pytest.approx(DEMAND)
    assert prog.total_utile == pytest.approx(DEMAND + 7.0)


def test_a_couloir_standing_as_a_leaf_does_demand_area():
    """The same room, placed as a room rather than as a spine, is a leaf."""
    flat = SlicingTree(
        Cut(Direction.V, False, (Leaf("Couloir"), Leaf("Sejour")))
    )
    assert sized_demand(programme(), flat) == pytest.approx(7.0 + 30.0)


def test_envelope_round_trips_through_the_footprint():
    fp = Footprint(2.0, 3.0, 11.0, 8.0)
    again = Footprint.from_envelope(fp.envelope_rect(P), P)
    assert (again.x, again.y, again.w, again.h) == pytest.approx(
        (fp.x, fp.y, fp.w, fp.h)
    )


def test_coverage_is_built_over_parcel():
    """Half the parcel built on is a coverage of 0.5."""
    site = parcel(20.0, 10.0)
    assert Footprint(0.0, 0.0, 10.0, 10.0).coverage(site) == pytest.approx(0.5)
    assert Footprint.of_parcel(site).coverage(site) == pytest.approx(1.0)


def test_a_footprint_needs_positive_extent():
    with pytest.raises(ValueError, match="positive extent"):
        Footprint(0.0, 0.0, 0.0, 5.0)


# --- the solve --------------------------------------------------------------


@pytest.mark.parametrize("aspect", [1.0, 1.25, 1.6, 2.0])
@pytest.mark.parametrize("size", [1.0, 1.4, 1.8, 2.5])
def test_the_solve_lands_on_the_demand(aspect, size):
    """Exact whatever the proportion, and whatever slack the parcel has.

    The parcel is given the same proportion as the building asked for, so this
    measures the solve and nothing else — a square building on a long thin site
    is a containment question and has its own test below.
    """
    gross = DEMAND * 1.38 * size
    h = (gross / aspect) ** 0.5
    site = parcel(gross / h, h)
    fp = fit_footprint(programme(), site, P, tree(), aspect=aspect)

    assert delivered(fp, programme(), site, P, tree()) == pytest.approx(
        DEMAND, abs=FP.FIT_TOL
    )
    assert fp.aspect == pytest.approx(aspect)
    assert fp.within(site)


def test_an_aspect_the_parcel_cannot_hold_is_not_an_infeasible_brief():
    """Wrong shape and too small are different failures and read differently.

    A square building on a 26.0 x 6.0 site: the area is amply there, the
    proportion is not. Reporting that as `InfeasibleBrief` would tell an
    architect to find a bigger site when what they need is a longer building.
    """
    site = parcel(26.0, 6.0)
    with pytest.raises(ValueError) as caught:
        fit_footprint(programme(), site, P, tree(), aspect=1.0)
    message = str(caught.value)
    assert not isinstance(caught.value, InfeasibleBrief)
    assert "the area is there" in message and "slack" in message

    # and the way out it names does work: the parcel's own proportion.
    assert "Omit `aspect`" in message
    assert fit_footprint(programme(), site, P, tree()).within(site)


def test_the_solve_is_a_handful_of_realises_not_a_search():
    """Four secant steps was the measurement; this is the guard on it.

    Counted as calls to `delivered`, which is one `realise` each — bracketing
    included, since that is part of what a caller pays.
    """
    calls = []
    real = FP.delivered
    FP.delivered = lambda *a, **k: (calls.append(1), real(*a, **k))[1]
    try:
        fit_footprint(programme(), parcel(13.0, 10.4), P, tree())
    finally:
        FP.delivered = real
    assert len(calls) <= 8, f"{len(calls)} realises to solve one unknown"


def test_the_solve_is_deterministic():
    site = parcel(13.0, 10.4)
    first = fit_footprint(programme(), site, P, tree())
    again = fit_footprint(programme(), site, P, tree())
    assert (first.x, first.y, first.w, first.h) == (again.x, again.y, again.w, again.h)


def test_a_bigger_parcel_gives_the_same_building_not_a_bigger_one():
    """The point of solving rather than scaling: rooms get what was asked.

    On the old behaviour the same programme on a parcel 2.5x its size produced
    rooms 2.9x too large, because the footprint was the site.
    """
    small = fit_footprint(programme(), parcel(13.0, 10.4), P, tree())
    large = fit_footprint(programme(), parcel(20.6, 16.5), P, tree(), aspect=1.25)
    assert small.area == pytest.approx(large.area, rel=1e-9)


# --- the headline -----------------------------------------------------------


def test_round_numbers_become_buildable():
    """An uncalibrated brief fails the area gate, and passes after one call.

    This is what could not be done before S14. The programme is round numbers
    on a parcel nobody matched to it; `fit_brief` is the whole calibration loop
    that every fixture in this repo used to spell out by hand.
    """
    raw = brief_on(13.0, 10.4)
    before = tree().realise(envelope_of(raw), raw, grid_for(raw))
    assert not AREA_GATE.check(before, raw), "the fixtures were calibrated for a reason"
    assert before.max_area_error(P) > AREA_TOLERANCE

    fitted = fit_brief(raw, tree())
    after = tree().realise(envelope_of(fitted), fitted, grid_for(fitted))
    assert after.max_area_error(P) == pytest.approx(0.0, abs=1e-9)
    assert AREA_GATE.check(after, fitted)
    assert fitted.programme is raw.programme, "the brief was fitted, not rewritten"


def test_fit_brief_keeps_the_building_on_the_site():
    fitted = fit_brief(brief_on(16.0, 13.0), tree())
    assert fitted.footprint is not None
    assert fitted.footprint.within(fitted.parcel)
    assert fitted.footprint.coverage(fitted.parcel) < 1.0


# --- when the site is too small ---------------------------------------------


def test_a_parcel_too_small_refuses_to_solve():
    with pytest.raises(InfeasibleBrief) as caught:
        fit_footprint(programme(), parcel(8.0, 6.4), P, tree())
    assert caught.value.budget.deficit > 0
    assert "DEFICIT" in caught.value.budget.explain()


def test_a_parcel_too_small_scales_the_programme_down():
    """Every room loses the same fraction, which is the honest answer."""
    site = parcel(8.0, 6.4)
    whole = Footprint.of_parcel(site)
    factor = scale_for(programme(), whole, site, P, tree())
    assert factor < 1.0

    scaled = fit_programme(programme(), whole, site, P, tree())
    for room in scaled.rooms:
        if room.nom == "Couloir":
            assert room.surface_utile == 7.0, "a band's declared area is untouched"
        else:
            original = programme().by_nom(room.nom).surface_utile
            assert room.surface_utile == pytest.approx(original * factor)


def test_fit_brief_falls_back_to_scaling():
    """No exception reaches the caller: a small site gives a smaller flat."""
    fitted = fit_brief(brief_on(8.0, 6.4), tree())
    assert fitted.footprint == Footprint.of_parcel(fitted.parcel)
    plan = tree().realise(envelope_of(fitted), fitted, grid_for(fitted))
    assert plan.max_area_error(P) == pytest.approx(0.0, abs=1e-9)
    assert fitted.programme.by_nom("Sejour").surface_utile < 30.0


# --- coverage ---------------------------------------------------------------


def test_coverage_is_a_gate_and_runs_early():
    """CLAUDE.md lists coverage among the gates; until S14 it did not exist."""
    names = [gate.name for gate in GATES]
    assert names[:2] == ["area", "coverage"], "both are float comparisons"


def test_coverage_passes_at_the_default_and_on_the_whole_parcel():
    """The default profile constrains nothing, so nothing that passed now fails.

    Building on the entire bounding box is a coverage of exactly 1.0, which is
    the value floating point is least likely to hit on the nose — the tolerance
    in the gate exists for this case.
    """
    raw = brief_on(13.0, 10.4)
    plan = tree().realise(envelope_of(raw), raw, grid_for(raw))
    assert COVERAGE_GATE.check(plan, raw)


def test_coverage_refuses_a_footprint_over_the_ces():
    site = parcel(16.0, 13.0)
    strict = replace(P, coverage_max=0.4)
    prog = programme()
    fitted = Brief(prog, site, strict, check_feasibility(prog, site, strict))
    fitted = fit_brief(fitted, tree())

    plan = tree().realise(envelope_of(fitted), fitted, grid_for(fitted))
    assert fitted.footprint.coverage(site) > 0.4
    assert not COVERAGE_GATE.check(plan, fitted)

    generous = replace(fitted, profile=replace(strict, coverage_max=0.9))
    assert COVERAGE_GATE.check(plan, generous)


# --- nothing before S14 moved -----------------------------------------------


def test_envelope_of_without_a_footprint_is_what_it_always_was():
    """The pre-S14 arithmetic, spelled out, against the branch that replaced it."""
    raw = brief_on(13.0, 10.4)
    assert raw.footprint is None

    inset = P.facade_t / 2
    minx, miny, maxx, maxy = raw.parcel.outline.bounds
    was = (
        minx + inset,
        miny + inset,
        (maxx - minx) - 2 * inset,
        (maxy - miny) - 2 * inset,
    )
    assert envelope_of(raw) == pytest.approx(was)


def test_grid_follows_the_footprint():
    """A grid anchored to a boundary the building does not touch means nothing."""
    fitted = fit_brief(brief_on(16.0, 13.0), tree())
    grid = grid_for(fitted)
    assert grid.origin == pytest.approx((fitted.footprint.x, fitted.footprint.y))
    assert grid.origin != pytest.approx(fitted.parcel.outline.bounds[:2])


# --- the coupling S14 had to break ------------------------------------------
#
# The fabric matched a wall to a parcel edge by allowing exactly one offset:
# `facade_t / 2`, the inset a building gets when it *is* its parcel. Nothing
# said so — it read as a constant — but it meant a footprint even a millimetre
# inside its site matched no edge at all: no orientation, no window may be hung,
# and no frontage on the entry edge, so nothing is reachable. Measured before
# the fix: a footprint 0.2 mm inside its parcel took the calibrated fixture in
# `test_search.py` from ten valid plans to none.


def test_a_building_set_back_from_its_parcel_still_faces_its_edges():
    fitted = fit_brief(brief_on(16.0, 13.0), tree())
    fabric = tree().realise(envelope_of(fitted), fitted, grid_for(fitted)).to_fabric(P)

    assert fitted.footprint.w < 16.0 and fitted.footprint.h < 13.0
    faced = facings(fabric)
    assert all(faced[nom] is not None for nom in faced), faced


def test_a_building_set_back_from_its_parcel_is_still_reachable():
    """The gate that a sub-millimetre setback used to break outright."""
    fitted = fit_brief(brief_on(16.0, 13.0), tree())
    plan = tree().realise(envelope_of(fitted), fitted, grid_for(fitted))
    assert REACHABLE_GATE.check(plan, fitted)


def test_the_slack_is_measured_not_assumed():
    """It is `facade_t / 2` when the building fills the parcel, and more when
    it does not — by exactly the setback, because that is where the axes are."""
    site = parcel(16.0, 13.0)
    prog = programme()
    brief = Brief(prog, site, P, check_feasibility(prog, site, P))

    whole = tree().realise(envelope_of(brief), brief, grid_for(brief)).to_fabric(P)
    assert whole._slack_on(0) == pytest.approx(P.facade_t / 2 + BOUND_TOL)

    inset = fit_brief(brief, tree())
    fabric = tree().realise(envelope_of(inset), inset, grid_for(inset)).to_fabric(P)
    setback = inset.parcel.outline.bounds[3] - (inset.footprint.y + inset.footprint.h)
    assert fabric._slack_on(2) == pytest.approx(
        setback + P.facade_t / 2 + BOUND_TOL
    ), "edge 2 is the top, which the building is set back from"


def test_fitting_does_not_change_what_a_calibrated_brief_generates():
    """The neutrality check: the same search, on a brief that never needed it.

    `test_search.py`'s fixture is calibrated by hand, so `fit_brief` should
    solve a footprint that is essentially its parcel and change nothing. It
    solves to within half a millimetre — and half a millimetre is precisely the
    amount that used to matter.
    """
    from planfgen.tests.test_search import apartment_brief, apartment_graph, seed_tree
    from planfgen.search import anneal

    raw = apartment_brief()
    fitted = fit_brief(raw, seed_tree())
    assert fitted.footprint.w < raw.parcel.outline.bounds[2], "genuinely inside"

    before = anneal(raw, seed_tree(), 200, seed=3, graph=apartment_graph())
    after = anneal(fitted, seed_tree(), 200, seed=3, graph=apartment_graph())
    assert len(after) == len(before) > 0
    assert after[0].scores.globale == pytest.approx(before[0].scores.globale)
