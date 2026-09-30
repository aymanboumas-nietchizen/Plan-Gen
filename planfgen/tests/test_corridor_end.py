"""A corridor ends at its last door (the architect, 2026-09-29).

"Tu ne peux pas laisser la fin des couloirs comme ça en cul de sac, c'est un
espace gâché qu'on peut ajouter à une chambre ou à la SDB." The stub is measured
from where the corridor is entered, with each room's door on its shared run as
near that origin as it goes; L6 puts the door exactly there, so the drawing and
the gate agree; and the constructor only builds corridors whose far end meets
circulation or a room across it whose door fits the end.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

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
from planfgen.brief.regulation import PROFILES
from planfgen.circulation import circulation_runs
from planfgen.circulation.shape import corridor_axis, door_interval, door_run
from planfgen.evaluate import CIRCULATION_GATE, STUB_ALLOWANCE, violation
from planfgen.fabric import WallKind
from planfgen.openings import place_doors
from planfgen.partition import PartitionPlan, StructuralGrid
from planfgen.tests.test_gates import SPINE_CELLS, cell
from planfgen.topology import ProgrammeGraph, Relation, RelationType

P = MA_PROFILE
F, C = WallKind.FACADE, WallKind.CLOISON


def plan_of(cells, rooms):
    programme = Programme([RoomSpec(n, k, a, "#888888") for n, k, a in rooms])
    parcel = Parcel(
        outline=Polygon([(0, 0), (8, 0), (8, 11), (0, 11)]),
        edges=[EdgeSpec(0, EdgeType.STREET), EdgeSpec(1, EdgeType.MITOYEN),
               EdgeSpec(2, EdgeType.COURT), EdgeSpec(3, EdgeType.MITOYEN)],
        north=0.0, entry_edge=0,
    )
    brief = Brief(programme, parcel, P, check_feasibility(programme, parcel, P))
    return PartitionPlan(cells, StructuralGrid.from_span(8.0, 11.0), (0.0, 0.0, 8.0, 11.0), brief), brief


SPINE_ROOMS = [("Couloir", RoomType.COULOIR, 12.0), ("SDB", RoomType.SDB, 20.0),
               ("Chambre", RoomType.CHAMBRE, 24.0), ("Sejour", RoomType.SEJOUR, 23.0)]


def spine():
    """A corridor from the street to the court, three rooms beside it: the last
    door is the sejour's, near its lower corner, and 2.5 m of corridor run on
    to the court facade."""
    return plan_of(SPINE_CELLS(), SPINE_ROOMS)


def capped():
    """The same corridor stopped at 7.30 m by the sejour taken across its end."""
    return plan_of([
        cell("Couloir", 0.0, 0.0, 1.4, 7.3, F, C, F, C),
        cell("SDB", 1.4, 0.0, 6.6, 3.4, C, F, F, C),
        cell("Chambre", 1.4, 3.4, 6.6, 3.9, C, F, C, C),
        cell("Sejour", 0.0, 7.3, 8.0, 3.7, F, F, C, F),
    ], SPINE_ROOMS)


def test_the_allowance_is_a_jamb_not_a_corridor_width():
    assert STUB_ALLOWANCE == pytest.approx(0.10)
    assert STUB_ALLOWANCE < min(p.corridor_clear for p in PROFILES.values())


def test_a_corridor_past_its_last_door_is_refused():
    plan, brief = spine()
    run = circulation_runs(plan.to_fabric(P)).runs[0]
    # the sejour's door, nearest the street: its clear run starts at 7.30 + 0.05
    last = 7.3 + P.cloison_t / 2 + P.door_module_for(RoomType.SEJOUR)
    assert run.stub == pytest.approx(11.0 - P.facade_t / 2 - last, abs=1e-6)
    assert run.stub > 2.0
    assert not CIRCULATION_GATE.check(plan, brief)
    assert violation(plan, brief) >= run.stub - STUB_ALLOWANCE - 1e-9, "metres steer the walk"


def test_a_room_alongside_does_not_hide_the_stub():
    """Before 2026-09-29 the sejour, running alongside to the facade, counted as
    serving the whole corridor: the stub read 0 wherever its door was."""
    plan, _ = spine()
    run = circulation_runs(plan.to_fabric(P)).runs[0]
    assert run.origin is not None and run.origin[1] < 0.2, "entered from the street"
    assert run.stub > P.corridor_clear, "and it would have failed even the old allowance"


def test_a_room_across_the_end_closes_the_corridor():
    plan, brief = capped()
    fabric = plan.to_fabric(P)
    assert fabric.door_capable("Couloir", "Sejour")
    assert circulation_runs(fabric).runs[0].stub == pytest.approx(0.0, abs=1e-9)
    assert CIRCULATION_GATE.check(plan, brief)


def _relations(fabric):
    band = next(n for n, s in fabric.spaces.items() if s.kind.names_band)
    rel = [Relation(band, n, RelationType.CONNECTED, 1.0)
           for n, s in fabric.spaces.items()
           if n != band and not s.kind.is_circulation and fabric.door_capable(band, n)]
    return SimpleNamespace(graph=ProgrammeGraph(rel))


def _doors_agree(fabric, profile) -> int:
    """Every door L6 hangs off a corridor is where the stub measure put it."""
    runs = {r.nom: r for r in circulation_runs(fabric).runs}
    checked = 0
    for door in place_doors(fabric, _relations(fabric), profile).doors:
        wall = door.wall
        for band, run in runs.items():
            space = fabric.spaces[band]
            if not any(w is wall for w in space.bounding) or run.origin is None:
                continue
            axis = corridor_axis(space)
            lo, hi = sorted((wall.p0[axis], wall.p1[axis]))
            if hi - lo <= 1e-9:
                continue                           # across the end
            other = next((n for n, sp in fabric.spaces.items()
                          if n != band and any(w is wall for w in sp.bounding)), None)
            if other is None or fabric.spaces[other].kind.is_circulation:
                continue
            kind = fabric.door_kind(band, other)
            frame = profile.door_frame_for(kind)
            module = door.leaf + 2 * frame
            start, stop = door_interval(door_run(fabric, band, other, wall, axis, module),
                                        module, run.origin)
            got = lo + door.span[0] - frame
            assert got == pytest.approx(start, abs=1e-6), (band, door.swing_into)
            checked += 1
    return checked


def test_l6_hangs_the_door_where_the_gate_measures_it():
    plan, _ = spine()
    assert _doors_agree(plan.to_fabric(P), P) == 3


def test_l6_and_the_gate_agree_on_real_plans():
    import planfgen.search.anneal  # noqa: F401  (the function shadows the module)
    from planfgen.search.construct import construct
    from planfgen.studio.pipeline import attempts
    from planfgen.tests.test_studio import preset_brief

    anneal = sys.modules["planfgen.search.anneal"]
    checked = 0
    for key in ("F3", "DEMO"):
        for name in sorted(PROFILES):
            brief, _ = preset_brief(key, PROFILES[name])
            for tree, fitting in attempts(brief)[:2]:
                b = fitting.brief
                rect = anneal.envelope_of(b)
                for t in [tree, *construct(b, rect, 1, tries=2)]:
                    try:
                        fabric = t.realise(rect, b, anneal.grid_for(b)).to_fabric(b.profile)
                    except ValueError:
                        continue
                    checked += _doors_agree(fabric, b.profile)
    assert checked > 20


def test_the_constructor_builds_no_corridor_to_a_blind_end():
    """Every band it builds ends at circulation, at the street beside the
    hub, or at a room across it whose door fits: none runs to a facade."""
    import planfgen.search.anneal  # noqa: F401
    from planfgen.search.construct import construct
    from planfgen.studio.pipeline import attempts
    from planfgen.tests.test_studio import preset_brief

    anneal = sys.modules["planfgen.search.anneal"]
    built = passed = 0
    for key in ("F3", "F4", "DEMO"):
        for name in sorted(PROFILES):
            brief, _ = preset_brief(key, PROFILES[name])
            for _, fitting in attempts(brief)[:2]:
                b = fitting.brief
                rect = anneal.envelope_of(b)
                for tree in construct(b, rect, 1, tries=2):
                    plan = tree.realise(rect, b, anneal.grid_for(b))
                    built += 1
                    passed += CIRCULATION_GATE.check(plan, b)
    assert built > 0 and passed == built, (passed, built)
