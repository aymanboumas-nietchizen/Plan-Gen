"""Every room its door, and the doors drawn are the walk the gate passed.

2026-09-30, found by planfgen-engine: in 98 of 108 generated plans some room
got no door at all. L5 walks ANY door-capable wall; L6 only hung doors for
CONNECTED relations. Now L6 hangs, for every room the relations leave
unentered, a door on the walk L5 proves (`circulation.access_tree`), and
`openings.unentered` asks L5's question of the doors actually drawn.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from planfgen.brief import MA_PROFILE, RoomType
from planfgen.brief.regulation import PROFILES
from planfgen.circulation import access_tree, reachable
from planfgen.evaluate import all_gates
from planfgen.fabric import WallAxis, WallKind
from planfgen.openings import Door, door_graph, free_slot, place_doors, place_openings, unentered
from planfgen.tests.test_gates import spine_flat, stranded_flat
from planfgen.topology import ProgrammeGraph, Relation, RelationType

P = MA_PROFILE


def no_relations():
    return SimpleNamespace(graph=ProgrammeGraph([]))


def test_with_no_relation_at_all_every_room_still_gets_its_door():
    fabric = spine_flat()
    report = place_doors(fabric, no_relations(), P)
    assert unentered(fabric, report) == []
    graph = door_graph(fabric, report)
    assert all(graph[n] for n in fabric.spaces), graph


def test_the_door_is_on_the_walk_reachability_proves():
    fabric = spine_flat()
    tree = access_tree(fabric)
    assert set(tree) == set(fabric.spaces) - {reachable(fabric).entry}
    assert all(tree[n] == "Couloir" for n in ("SDB", "Chambre", "Sejour"))
    graph = door_graph(fabric, place_doors(fabric, no_relations(), P))
    for room, parent in tree.items():
        assert parent in graph[room]


def test_a_relation_the_walls_cannot_host_is_named_and_the_room_entered_anyway():
    fabric = spine_flat()
    wish = ProgrammeGraph([Relation("SDB", "Sejour", RelationType.CONNECTED, 1.0)])
    report = place_doors(fabric, SimpleNamespace(graph=wish), P)
    assert any(e.startswith("SDB~Sejour") for e in report.errors)
    assert unentered(fabric, report) == []


def test_a_room_the_gate_strands_is_still_unentered():
    fabric = stranded_flat()
    report = place_doors(fabric, no_relations(), P)
    assert "Cellier" in unentered(fabric, report)


def test_the_architects_door_is_preferred_where_there_is_a_choice():
    """Sejour could be entered from the corridor; asked for from nowhere else,
    it is. A preferred pair wins over the name order at the same depth."""
    fabric = spine_flat()
    assert access_tree(fabric, {frozenset(("Couloir", "Sejour"))})["Sejour"] == "Couloir"


def test_two_doors_never_cut_the_same_stretch_of_one_wall():
    """From opposite faces their quarter-discs do not meet; the holes would."""
    wall = WallAxis((0.0, 0.0), (3.0, 0.0), WallKind.CLOISON)
    first = Door(wall, 0.5, 0.83, "A", swing_side=-1)
    t = free_slot(wall, [first], 0.83, 0.05)
    assert t is not None
    probe = Door(wall, t, 0.83, "", swing_side=1)
    assert probe.span[0] - 0.05 >= first.span[1] - 1e-9 or probe.span[1] + 0.05 <= first.span[0] + 1e-9


def test_a_door_stands_clear_of_the_walls_that_meet_its_wall():
    """Given the clear run, the frame starts at the face of the wall meeting
    this one, not at the axis crossing inside its thickness."""
    wall = WallAxis((0.0, 0.0), (0.0, 3.0), WallKind.CLOISON)
    t = free_slot(wall, [], 0.83, 0.05, run=(0.15, 2.9))
    door = Door(wall, t, 0.83, "")
    assert door.span[0] - 0.05 >= 0.15 - 1e-9
    # a run too short for the module falls back to the whole axis, as before
    assert free_slot(wall, [], 0.83, 0.05, run=(0.15, 0.6)) is not None


def _passing_plans():
    """Plans that pass every gate: constructed trees for the presets, on a
    corner lot so every preset lights its rooms."""
    import planfgen.search.anneal  # noqa: F401  (the function shadows the module)
    from planfgen.search.construct import construct
    from planfgen.studio.pipeline import attempts
    from planfgen.studio.presets import PRESETS
    from planfgen.tests.test_studio import preset_brief

    anneal = sys.modules["planfgen.search.anneal"]
    from dataclasses import replace

    from planfgen.brief import EdgeSpec, EdgeType, check_feasibility

    for key in sorted(PRESETS):
        for name in sorted(PROFILES):
            brief, graph = preset_brief(key, PROFILES[name])
            edges = list(brief.parcel.edges)
            edges[1] = EdgeSpec(1, EdgeType.GARDEN)
            parcel = replace(brief.parcel, edges=edges)
            brief = replace(brief, parcel=parcel,
                            budget=check_feasibility(brief.programme, parcel, brief.profile))
            for _, fitting in attempts(brief)[:1]:
                b = fitting.brief
                rect = anneal.envelope_of(b)
                for tree in construct(b, rect, 1, tries=3):
                    result = anneal.evaluate(tree, b, anneal.grid_for(b), graph, 0)
                    if result is not None:       # passes every gate, on its own footprint
                        assert all_gates(result.plan, result.brief)[0]
                        yield result.plan.to_fabric(b.profile), graph, result.brief


def test_every_plan_that_passes_the_gates_is_entered_through_its_drawn_doors():
    checked = 0
    for fabric, graph, brief in _passing_plans():
        report = place_openings(fabric, SimpleNamespace(graph=graph), brief.profile,
                                brief.programme)
        assert unentered(fabric, report) == [], report.explain()
        rooms = [n for n, s in fabric.spaces.items() if not s.kind.is_circulation]
        drawn = door_graph(fabric, report)
        assert all(drawn[n] for n in rooms)
        checked += 1
    assert checked >= 5
