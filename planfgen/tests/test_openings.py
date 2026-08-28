"""L6 tests — doors that swing free, windows only where the edge allows.

The legality test is the one that matters. A window on a MITOYEN is not a
low-scoring plan, it is a hole through the neighbour's building, and a room that
needs daylight and has nowhere to take it is a mistake with a name rather than a
warning to be weighed against something else.
"""

from __future__ import annotations

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
from planfgen.fabric import WallAxis, WallKind
from planfgen.openings import (
    ENTRY_LEAF,
    Door,
    OpeningReport,
    Window,
    free_slot,
    needs_daylight,
    openable_walls,
    place_doors,
    place_openings,
    place_windows,
    required_glazing,
    size_windows,
)
from planfgen.partition import PartitionPlan, SpaceCell, StructuralGrid
from planfgen.topology import ProgrammeGraph, Relation, RelationType as R, TopologyPlan

from planfgen.tests.test_services import ROOMS, flat

P = MA_PROFILE
F, C = WallKind.FACADE, WallKind.CLOISON


def topology_for(relations: list[Relation], rooms=None) -> TopologyPlan:
    rooms = rooms or ROOMS
    programme = Programme([RoomSpec(n, k, a, "#888888") for n, k, a in rooms])
    return TopologyPlan.build(programme, ProgrammeGraph(relations), rooms[0][0])


FLAT_RELATIONS = [
    Relation("Couloir", "Sejour", R.CONNECTED),
    Relation("Couloir", "Cuisine", R.CONNECTED),
    Relation("Couloir", "Ch1", R.CONNECTED),
    Relation("Couloir", "Ch2", R.CONNECTED),
    Relation("Couloir", "SDB", R.CONNECTED),
    Relation("SDB", "WC", R.CONNECTED),
    Relation("Sejour", "Cuisine", R.CONNECTED),
]


def cell(nom, x, y, w, h, left, right, bottom, top) -> SpaceCell:
    return SpaceCell(
        nom, x, y, w, h, {"left": left, "right": right, "bottom": bottom, "top": top}
    )


def shelf_flat():
    """A placard 0.63 m tall: real contact with the sejour, no way through it."""
    rooms = [
        ("Placard", RoomType.CELLIER, 1.8),
        ("Chambre", RoomType.CHAMBRE, 15.0),
        ("Sejour", RoomType.SEJOUR, 28.0),
    ]
    programme = Programme([RoomSpec(n, k, a, "#888888") for n, k, a in rooms])
    parcel = Parcel(
        outline=Polygon([(0, 0), (8, 0), (8, 6), (0, 6)]),
        edges=[EdgeSpec(i, EdgeType.STREET) for i in range(4)],
        north=0.0,
        entry_edge=0,
    )
    brief = Brief(programme, parcel, P, check_feasibility(programme, parcel, P))
    cells = [
        cell("Placard", 0, 0, 3, 0.63, F, C, F, C),
        cell("Chambre", 0, 0.63, 3, 5.37, F, C, C, F),
        cell("Sejour", 3, 0, 5, 6, C, F, F, F),
    ]
    plan = PartitionPlan(cells, StructuralGrid.from_span(8, 6), (0.0, 0.0, 8.0, 6.0), brief)
    return plan.to_fabric(P), rooms


# --- glazing arithmetic -----------------------------------------------------


def test_required_glazing_is_the_ratio_of_the_floor():
    class _Room:
        surface_utile = 20.00
        kind = RoomType.SEJOUR

    assert P.daylight_ratio == 0.125
    assert required_glazing(_Room(), P) == pytest.approx(2.50, abs=1e-9)


def test_head_and_allege_are_regulation_values():
    """CLAUDE.md: regulation values live only in brief/regulation.py."""
    assert P.allege_h == 1.00 and P.head_h == 2.20
    assert P.glazing_height == pytest.approx(1.20)


def test_size_windows_delivers_what_the_room_owes():
    fabric = flat()
    sejour = fabric.spaces["Sejour"]
    windows = size_windows(sejour, openable_walls(fabric, sejour), P)

    assert windows
    assert sum(w.glazing for w in windows) == pytest.approx(
        required_glazing(sejour, P), abs=1e-9
    )
    for window in windows:
        assert window.allege == P.allege_h and window.head == P.head_h
        assert window.width <= window.wall.length - 2 * P.door_jamb


def test_a_window_needs_a_head_above_its_allege():
    wall = WallAxis((0, 0), (4, 0), WallKind.FACADE)
    with pytest.raises(ValueError, match="not above allege"):
        Window(wall, 0.5, 1.2, allege=2.20, head=1.00)
    with pytest.raises(ValueError, match="0..1"):
        Window(wall, 1.4, 1.2, allege=1.0, head=2.2)


# --- THE LEGALITY TEST ------------------------------------------------------


def test_no_window_ever_lands_on_a_mitoyen_edge():
    """A window on a party wall is a hole through the neighbour's building."""
    fabric = flat()
    assert not fabric.parcel.openable(1) and not fabric.parcel.openable(3)

    report = place_windows(fabric, P)
    for window in report.windows:
        assert window.wall.kind is WallKind.FACADE
        if window.wall.is_vertical:
            assert window.wall.p0[0] not in (0.0, 12.0), "the two mitoyen lines"
        for edge in (1, 3):
            assert not any(
                w is window.wall
                for space in fabric.spaces.values()
                for w in fabric.walls_on_edge(space, edge)
            )


def test_a_daylight_room_with_only_a_mitoyen_is_an_error_not_a_warning():
    fabric = flat()
    ch2 = fabric.spaces["Ch2"]
    assert needs_daylight(ch2)
    assert openable_walls(fabric, ch2) == [], "it only touches the party wall"

    report = place_windows(fabric, P)
    assert not report.ok
    assert any(e.startswith("Ch2:") and "no openable exterior wall" in e
               for e in report.errors), report.errors
    assert not any(w.wall in ch2.bounding for w in report.windows)


def test_rooms_that_do_reach_a_legal_edge_get_their_glass():
    fabric = flat()
    report = place_windows(fabric, P)
    lit = {id(w.wall) for w in report.windows}

    for nom in ("Sejour", "Cuisine", "Ch1"):
        space = fabric.spaces[nom]
        assert any(id(w) in lit for w in space.bounding), nom


def test_the_brief_daylight_flag_beats_the_kind_default():
    """A Space carries a kind, not the line of programme it came from."""
    fabric = flat()
    dark = Programme(
        [
            RoomSpec(n, k, a, "#888888", daylight=False)
            for n, k, a in ROOMS
        ]
    )
    report = place_windows(fabric, P, programme=dark)
    assert report.windows == [] and report.errors == []


# --- doors ------------------------------------------------------------------


def test_one_door_per_connected_relation_plus_the_front_door():
    fabric = flat()
    report = place_doors(fabric, topology_for(FLAT_RELATIONS), P)

    assert report.ok, report.errors
    assert len(report.doors) == len(FLAT_RELATIONS) + 1
    entry = [d for d in report.doors if d.leaf == ENTRY_LEAF]
    assert len(entry) == 1
    assert entry[0].wall.kind is WallKind.FACADE
    assert entry[0].wall.p0[1] == pytest.approx(0.0), "on the street edge"


def test_a_door_is_centred_on_the_run_it_shares():
    fabric = flat()
    report = place_doors(fabric, topology_for(FLAT_RELATIONS), P)
    door = next(d for d in report.doors if d.swing_into == "SDB")

    low, high = door.span
    assert high - low == pytest.approx(P.door_leaf, abs=1e-9)
    assert low >= 0 and high <= door.wall.length + 1e-9


def test_place_doors_refuses_a_sixty_three_centimetre_run_and_says_so():
    """Contact is not access. ARCHITECTURE section 1's whole complaint."""
    fabric, rooms = shelf_flat()
    assert fabric.shared_wall_length("Placard", "Sejour") == pytest.approx(0.63, abs=1e-9)

    topology = topology_for(
        [
            Relation("Placard", "Sejour", R.CONNECTED),
            Relation("Chambre", "Sejour", R.CONNECTED),
        ],
        rooms,
    )
    report = place_doors(fabric, topology, P)

    refused = [e for e in report.errors if e.startswith("Placard~Sejour")]
    assert len(refused) == 1
    assert "0.63" in refused[0] and "1.00" in refused[0]
    assert not any(d.swing_into == "Placard" for d in report.doors)
    assert any(d.swing_into == "Sejour" for d in report.doors), "the 5.37 m run is fine"


def test_a_relation_naming_a_room_the_plan_lacks_is_reported():
    fabric = flat()
    topology = topology_for(FLAT_RELATIONS + [])
    topology.graph.relations.append(Relation("Couloir", "Garage", R.CONNECTED))
    report = place_doors(fabric, topology, P)
    assert any("no such room" in e for e in report.errors)


# --- clearance --------------------------------------------------------------


def test_a_clearance_box_is_the_opening_by_the_leaf_on_the_swing_side():
    wall = WallAxis((0, 0), (4, 0), WallKind.CLOISON)
    door = Door(wall, t=0.5, leaf=0.80, swing_into="Sejour", swing_side=1)

    assert door.position() == pytest.approx((2.0, 0.0))
    assert door.clearance_box() == pytest.approx((1.6, 0.0, 2.4, 0.8), abs=1e-9)

    other_side = Door(wall, t=0.5, leaf=0.80, swing_into="Cuisine", swing_side=-1)
    assert other_side.clearance_box() == pytest.approx((1.6, -0.8, 2.4, 0.0), abs=1e-9)
    assert not door.clashes_with(other_side), "opposite sides never clash"


def test_two_doors_on_one_wall_do_not_overlap():
    """THE clearance contract. free_slot is what keeps them apart."""
    wall = WallAxis((0, 0), (6, 0), WallKind.CLOISON)
    first = Door(wall, t=0.2, leaf=0.80, swing_into="A", swing_side=1)

    t = free_slot(wall, [first], 0.80, P.door_jamb)
    assert t is not None
    second = Door(wall, t=t, leaf=0.80, swing_into="B", swing_side=1)

    assert not first.clashes_with(second)
    assert not second.clashes_with(first)
    a, b = first.clearance_box(), second.clearance_box()
    assert a[2] <= b[0] + 1e-9 or b[2] <= a[0] + 1e-9


def test_a_wall_too_short_for_a_leaf_offers_no_slot():
    short = WallAxis((0, 0), (0.90, 0), WallKind.CLOISON)
    assert free_slot(short, [], P.door_leaf, P.door_jamb) is None
    assert short.length < P.door_module


def test_every_pair_of_doors_in_a_real_plan_swings_clear():
    fabric = flat()
    report = place_doors(fabric, topology_for(FLAT_RELATIONS), P)

    for i, first in enumerate(report.doors):
        for second in report.doors[i + 1 :]:
            if first.wall is second.wall:
                assert not first.clashes_with(second), (first.swing_into, second.swing_into)


# --- the report -------------------------------------------------------------


def test_place_openings_reports_doors_and_windows_together():
    fabric = flat()
    report = place_openings(fabric, topology_for(FLAT_RELATIONS), P)

    assert isinstance(report, OpeningReport)
    assert len(report.doors) == len(FLAT_RELATIONS) + 1
    assert report.windows
    assert not report.ok, "Ch2 still has nowhere to take daylight"
    assert "Ch2" in report.explain()


def test_a_clean_report_says_so():
    assert OpeningReport().ok
    assert OpeningReport().explain() == "0 doors, 0 windows"
