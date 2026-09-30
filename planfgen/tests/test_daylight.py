"""Daylight is a gate (the architect, 2026-09-29): decret 2-64-445 ART. 7.

Every habitable room and the kitchen is lit to `daylight_ratio` of its floor
and never under `MIN_GLAZING`; a bay under `MIN_WINDOW_DIMENSION` is not a
window. The gate asks it of partition cells; L6 draws the windows on the wall
graph; the constructor asks it of regions. These tests pin the rule, the gate,
and — on real plans — that the three agree.
"""

from __future__ import annotations

import sys

import pytest
from shapely.geometry import Polygon

from planfgen.brief import (
    MA_PROFILE,
    Brief,
    EdgeSpec,
    EdgeType,
    Parcel,
    Programme,
    RoomSpec,
    RoomType,
    check_feasibility,
)
from planfgen.brief.regulation import MIN_GLAZING, MIN_WINDOW_DIMENSION, PROFILES
from planfgen.evaluate import (
    DAYLIGHT_GATE,
    GATES,
    daylight_capacity,
    daylight_shortfall,
    violation,
)
from planfgen.openings import (
    DAYLIGHT_KINDS,
    glazing_owed,
    openable_walls,
    place_windows,
    size_windows,
    width_owed,
    window_capacity,
    window_widths,
)
from planfgen.openings.window import net_run
from planfgen.partition import PartitionPlan, StructuralGrid
from planfgen.tests.test_gates import SPINE_CELLS

P = MA_PROFILE


# --- the rule, as arithmetic -------------------------------------------------


def test_the_rule_reads_regulation_py():
    assert MIN_GLAZING == 1.00 and MIN_WINDOW_DIMENSION == 0.35
    assert glazing_owed(4.0, P) == pytest.approx(1.00), "never under 1 m2"
    assert glazing_owed(20.0, P) == pytest.approx(2.50)
    assert width_owed(20.0, P) == pytest.approx(2.50 / P.glazing_height)
    casa = PROFILES["casablanca"]
    assert glazing_owed(24.0, casa) == pytest.approx(4.0), "1/6 in Casablanca"


def test_a_run_too_short_for_a_window_carries_none():
    assert window_capacity(2.0, P) == pytest.approx(2.0 - 2 * P.door_jamb)
    assert window_capacity(0.55, P) == pytest.approx(0.35)
    assert window_capacity(0.54, P) == 0.0, "0.34 m between jambs is not a window"


@pytest.mark.parametrize("caps,owed", [
    ([3.0], 1.0), ([3.0, 2.0], 4.0), ([5.0, 0.35], 5.01), ([0.5, 0.5], 0.6),
    ([2.0, 1.0], 9.0), ([], 1.0), ([0.0, 1.2], 0.9),
])
def test_window_widths_respect_the_minimum_and_the_wall(caps, owed):
    widths = window_widths(caps, owed)
    assert len(widths) == len(caps)
    for w, cap in zip(widths, caps):
        assert w == 0.0 or MIN_WINDOW_DIMENSION - 1e-9 <= w <= cap + 1e-9
    assert sum(widths) >= min(owed, sum(caps)) - 1e-9


# --- the gate ----------------------------------------------------------------


def spine_plan(east: EdgeType = EdgeType.MITOYEN):
    """test_gates' spine: SDB, Chambre, Sejour stacked off a left corridor, 8 x
    11 m, street south and court north. The Chambre in the middle touches only
    the east boundary, so it is lit iff that boundary may be pierced."""
    rooms = [("Couloir", RoomType.COULOIR, 12.0), ("SDB", RoomType.SDB, 20.0),
             ("Chambre", RoomType.CHAMBRE, 24.0), ("Sejour", RoomType.SEJOUR, 23.0)]
    programme = Programme([RoomSpec(n, k, a, "#888888") for n, k, a in rooms])
    parcel = Parcel(
        outline=Polygon([(0, 0), (8, 0), (8, 11), (0, 11)]),
        edges=[EdgeSpec(0, EdgeType.STREET), EdgeSpec(1, east),
               EdgeSpec(2, EdgeType.COURT), EdgeSpec(3, EdgeType.MITOYEN)],
        north=0.0, entry_edge=0,
    )
    brief = Brief(programme, parcel, P, check_feasibility(programme, parcel, P))
    plan = PartitionPlan(SPINE_CELLS(), StructuralGrid.from_span(8.0, 11.0),
                         (0.0, 0.0, 8.0, 11.0), brief)
    return plan, brief


def test_a_bedroom_without_a_window_is_refused():
    plan, brief = spine_plan()
    assert daylight_shortfall(plan, brief) == {"Chambre": 1.0, "Sejour": 0.0}
    assert not DAYLIGHT_GATE.check(plan, brief)
    assert violation(plan, brief) > 0, "the guided walk sees it"


def test_the_same_bedroom_on_a_garden_is_lit():
    plan, brief = spine_plan(EdgeType.GARDEN)
    assert DAYLIGHT_GATE.check(plan, brief)
    chambre = next(c for c in plan.cells if c.nom == "Chambre")
    assert daylight_capacity(chambre, plan, brief) == pytest.approx(
        window_capacity(3.9 - 0.05 - 0.05, P))


def test_only_the_rooms_the_law_lights_are_asked():
    """The SDB and the corridor touch only the street and a party wall, and are
    not asked; decret ART. 7 names habitable rooms and the kitchen."""
    plan, brief = spine_plan(EdgeType.GARDEN)
    assert set(daylight_shortfall(plan, brief)) == {"Chambre", "Sejour"}
    assert DAYLIGHT_KINDS == {RoomType.SEJOUR, RoomType.CHAMBRE,
                              RoomType.CHAMBRE_PRINCIPALE, RoomType.BUREAU,
                              RoomType.CUISINE}


def test_daylight_runs_after_furniture_and_before_any_wall_is_built():
    names = [g.name for g in GATES]
    assert names.index("furniture") < names.index("daylight") < names.index("circulation")


# --- the gate, L6 and the constructor agree on real plans -----------------------


def _real_plans():
    """Seed and constructed trees for every preset on every profile, realised
    on the envelopes the studio would try: passing and failing plans alike."""
    import planfgen.search.anneal  # noqa: F401  (the function shadows the module)
    from planfgen.search.construct import construct
    from planfgen.studio.pipeline import attempts
    from planfgen.studio.presets import PRESETS
    from planfgen.tests.test_studio import preset_brief

    anneal = sys.modules["planfgen.search.anneal"]
    for key in sorted(PRESETS):
        for name in sorted(PROFILES):
            brief, _ = preset_brief(key, PROFILES[name])
            for tree, fitting in attempts(brief)[:2]:
                b = fitting.brief
                rect = anneal.envelope_of(b)
                for t in [tree, *construct(b, rect, 1, tries=2)]:
                    try:
                        plan = t.realise(rect, b, anneal.grid_for(b))
                        fabric = plan.to_fabric(b.profile)
                    except ValueError:
                        continue
                    yield plan, fabric, b


def test_gate_and_windows_agree_on_real_plans():
    compared = refused = 0
    for plan, fabric, brief in _real_plans():
        report = place_windows(fabric, brief.profile)
        blind = {e.split(":")[0] for e in report.errors}
        shortfall = daylight_shortfall(plan, brief)
        for cell in plan.cells:
            space = fabric.spaces[cell.nom]
            if space.kind not in DAYLIGHT_KINDS:
                continue
            walls = openable_walls(fabric, space)
            drawn = sum(window_capacity(net_run(w, space), brief.profile) for w in walls)
            assert daylight_capacity(cell, plan, brief) == pytest.approx(drawn, abs=1e-6)
            assert (shortfall[cell.nom] > 1e-9) == (cell.nom in blind), cell.nom
            for window in size_windows(space, walls, brief.profile):
                assert window.width >= MIN_WINDOW_DIMENSION - 1e-9
            compared += 1
        refused += not DAYLIGHT_GATE.check(plan, brief)
    assert compared > 100 and refused > 0, (compared, refused)


def test_every_constructed_tree_lights_its_rooms():
    """The constructor's leaf rule is the gate's: nothing it builds is blind."""
    import planfgen.search.anneal  # noqa: F401
    from planfgen.search.construct import construct
    from planfgen.studio.pipeline import attempts
    from planfgen.tests.test_studio import preset_brief

    anneal = sys.modules["planfgen.search.anneal"]
    built = 0
    for name in sorted(PROFILES):
        brief, _ = preset_brief("DEMO", PROFILES[name])
        for _, fitting in attempts(brief)[:1]:
            b = fitting.brief
            rect = anneal.envelope_of(b)
            for tree in construct(b, rect, 1, tries=3):
                plan = tree.realise(rect, b, anneal.grid_for(b))
                assert DAYLIGHT_GATE.check(plan, b), daylight_shortfall(plan, b)
                built += 1
            # a unit with no side that may take a window builds nothing lit
            assert construct(b, rect, 1, tries=3, open_sides=frozenset()) == []
    assert built > 0
