"""L4 tests — shafts, wet walls, and the R+n set comparison.

The fixture is a seven-space flat on 12.00 x 9.00 with a vertical spine: the
cuisine on the day side, the SDB and the WC paired on the night side. Two wet
clusters, because the corridor separates the kitchen from the bathrooms, which
is what an apartment normally looks like and what makes the clustering worth
testing at all.
"""

from __future__ import annotations

from copy import deepcopy

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
from planfgen.fabric import WallKind
from planfgen.partition import PartitionPlan, SpaceCell, StructuralGrid
from planfgen.services import (
    SHAFT_SIDE,
    Conflict,
    Level,
    Shaft,
    ShaftType,
    assign_stack_ids,
    assign_wet_walls,
    place_shafts,
    shaft_stack_id,
    stable,
    stack_conflicts,
    wall_stack_id,
    wet_clusters,
    wet_report,
)

P = MA_PROFILE
F, C = WallKind.FACADE, WallKind.CLOISON
W, H = 12.0, 9.0

ROOMS = [
    ("Sejour", RoomType.SEJOUR, 24.0),
    ("Cuisine", RoomType.CUISINE, 19.0),
    ("Couloir", RoomType.COULOIR, 10.0),
    ("Ch1", RoomType.CHAMBRE_PRINCIPALE, 22.0),
    ("Ch2", RoomType.CHAMBRE, 14.0),
    ("SDB", RoomType.SDB, 7.0),
    ("WC", RoomType.WC, 7.0),
]


def cell(nom, x, y, w, h, left, right, bottom, top, band=False) -> SpaceCell:
    return SpaceCell(
        nom, x, y, w, h,
        {"left": left, "right": right, "bottom": bottom, "top": top},
        is_band=band,
    )


def grid() -> StructuralGrid:
    return StructuralGrid.from_span(W, H)


def flat():
    programme = Programme([RoomSpec(n, k, a, "#888888") for n, k, a in ROOMS])
    parcel = Parcel(
        outline=Polygon([(0, 0), (W, 0), (W, H), (0, H)]),
        edges=[
            EdgeSpec(0, EdgeType.STREET),
            EdgeSpec(1, EdgeType.MITOYEN),
            EdgeSpec(2, EdgeType.COURT),
            EdgeSpec(3, EdgeType.MITOYEN),
        ],
        north=0.0,
        entry_edge=0,
    )
    brief = Brief(programme, parcel, P, check_feasibility(programme, parcel, P))
    cells = [
        cell("Sejour", 0, 0, 5, 5, F, C, F, C),
        cell("Cuisine", 0, 5, 5, 4, F, C, C, F),
        cell("Couloir", 5, 0, 1.3, 9, C, C, F, F, band=True),
        cell("Ch1", 6.3, 5, 5.7, 4, C, F, C, F),
        cell("Ch2", 6.3, 2.5, 5.7, 2.5, C, F, C, C),
        cell("SDB", 6.3, 0, 2.85, 2.5, C, C, F, C),
        cell("WC", 9.15, 0, 2.85, 2.5, C, F, F, C),
    ]
    plan = PartitionPlan(cells, grid(), (0.0, 0.0, W, H), brief)
    return plan.to_fabric(P)


def wall_between(fabric, a: str, b: str):
    return fabric.graph.wall_between(
        fabric.spaces[a].axis_polygon, fabric.spaces[b].axis_polygon
    )


# --- shafts -----------------------------------------------------------------


def test_the_corridor_splits_the_flat_into_two_wet_clusters():
    assert wet_clusters(flat()) == [["Cuisine"], ["SDB", "WC"]]


def test_one_plumbing_shaft_per_wet_cluster():
    fabric = flat()
    shafts = place_shafts(fabric, P)

    assert len(shafts) == 2
    assert all(s.kind is ShaftType.PLUMBING for s in shafts)
    assert all((s.w, s.h) == (SHAFT_SIDE, SHAFT_SIDE) for s in shafts)


def test_a_paired_cluster_puts_its_shaft_on_the_wall_the_two_rooms_share():
    """One stack serving both is the whole reason to cluster them."""
    fabric = flat()
    shared = wall_between(fabric, "SDB", "WC")
    shaft = next(s for s in place_shafts(fabric, P) if s.on_wall(shared))

    assert shaft.on_wall(shared)
    assert shaft.centre == pytest.approx((9.15, 1.25), abs=1e-9)
    for nom in ("SDB", "WC"):
        assert any(shaft.on_wall(w) for w in fabric.spaces[nom].bounding)


def test_a_lone_wet_room_puts_its_shaft_on_a_wall_that_could_not_take_a_window():
    """The cuisine has no wet neighbour, so the party wall costs it nothing."""
    fabric = flat()
    shaft = next(s for s in place_shafts(fabric, P) if s.centre[0] < 1.0)

    on = [w for w in fabric.spaces["Cuisine"].bounding if shaft.on_wall(w)]
    assert on, "the shaft sits on one of the kitchen's own walls"
    assert all(w.kind is WallKind.FACADE for w in on)
    assert not fabric.parcel.openable(3), "edge 3 is the mitoyen"


def test_every_wet_room_ends_with_a_wall_on_a_shaft():
    """THE contract of this layer, and the reason the clustering exists."""
    fabric = flat()
    report = wet_report(fabric, place_shafts(fabric, P))

    assert set(report) == {"Cuisine", "SDB", "WC"}
    assert all(report.values()), report
    assert "Ch1" not in report, "a chambre has no opinion about plumbing"


# --- wet walls --------------------------------------------------------------


def test_assign_wet_walls_retypes_the_sdb_wc_wall():
    fabric = flat()
    shared = wall_between(fabric, "SDB", "WC")
    assert shared.kind is WallKind.CLOISON

    assign_wet_walls(fabric, place_shafts(fabric, P))
    assert shared.kind is WallKind.WET


def test_a_facade_is_never_retyped_wet():
    """A wall between a bathroom and the street is the outside, not a wet wall."""
    fabric = flat()
    facades = [w for w in fabric.graph.walls if w.kind is WallKind.FACADE]
    assign_wet_walls(fabric, place_shafts(fabric, P))
    assert all(w.kind is WallKind.FACADE for w in facades)


def test_retyping_costs_the_rooms_area_and_says_so():
    """WET is 0.20 against a cloison's 0.10, so both rooms lose 0.05 of width.

    The spaces are re-solidified, because leaving them stale would break L3's
    guarantee that its net areas are measured rather than remembered.
    """
    fabric = flat()
    before = {nom: sp.surface_utile for nom, sp in fabric.spaces.items()}
    assign_wet_walls(fabric, place_shafts(fabric, P))

    for nom in ("SDB", "WC"):
        lost = before[nom] - fabric.spaces[nom].surface_utile
        net_w, net_h = fabric.spaces[nom].net_dims()
        assert lost == pytest.approx(0.05 * net_h, abs=1e-6), nom
    for nom in ("Ch1", "Ch2", "Sejour"):
        assert fabric.spaces[nom].surface_utile == pytest.approx(before[nom])


def test_assigning_twice_changes_nothing_further():
    fabric = flat()
    shafts = place_shafts(fabric, P)
    assign_wet_walls(fabric, shafts)
    once = {nom: sp.surface_utile for nom, sp in fabric.spaces.items()}
    assign_wet_walls(fabric, shafts)
    assert {nom: sp.surface_utile for nom, sp in fabric.spaces.items()} == once


# --- stack ids --------------------------------------------------------------


def test_only_bearing_walls_get_a_stack_id():
    """Partitions do not stack, which is why WallKind.bearing exists."""
    fabric = flat()
    level = Level(0, 2.80, fabric, place_shafts(fabric, P))
    assign_stack_ids(level, grid())

    for wall in fabric.graph.walls:
        if wall.kind.bearing:
            assert wall.stack_id and wall.stack_id[0] in "VH"
        else:
            assert wall.stack_id is None


def test_ids_name_the_line_not_the_segment():
    """A bearing run split by noding stacks as one line or not at all."""
    fabric = flat()
    level = Level(0, 2.80, fabric, place_shafts(fabric, P))
    assign_stack_ids(level, grid())

    bottom = [
        w for w in fabric.graph.walls if w.is_horizontal and abs(w.p0[1]) < 1e-9
    ]
    assert len(bottom) > 1, "the street facade is several axes after noding"
    assert len({w.stack_id for w in bottom}) == 1 == len({"H:y=0.00"} & {w.stack_id for w in bottom})


def test_a_shaft_id_keeps_the_shaft_where_it_is():
    """Snapping a shaft to a 4.00 x 4.50 structural module would move it metres.

    Grid-aligned coordinates take the grid line; everything else keeps its own,
    rounded to the centimetre. Two bearing lines 2.00 m apart must not collapse
    onto one id, or the conflict this module looks for becomes invisible.
    """
    g = grid()
    assert (g.module_x, g.module_y) == (4.0, 4.5)

    shaft = Shaft(9.0, 1.1, SHAFT_SIDE, SHAFT_SIDE, ShaftType.PLUMBING)
    assert shaft_stack_id(shaft, g) == "SH:9.15,1.25"

    assert stable(8.0, g, "x") == 8.0, "on a grid line, so it takes the line"
    assert stable(0.15, g, "x") == 0.15, "a facade axis is not on the grid"
    assert stable(1.50, g, "x") != stable(0.15, g, "x"), "no collision"


# --- the R+n comparison -----------------------------------------------------


def levels() -> tuple[Level, Level]:
    fabric = flat()
    ground = Level(0, 2.80, fabric, place_shafts(fabric, P))
    assign_stack_ids(ground, grid())
    upper = deepcopy(ground)
    upper.index = 1
    return ground, upper


def test_a_level_never_conflicts_with_a_copy_of_itself():
    """THE R+n test. If this is not empty the ids are not stable and the whole
    scheme is worthless."""
    ground, upper = levels()
    assert stack_conflicts(ground, upper) == []
    assert stack_conflicts(ground, deepcopy(ground)) == []
    assert ground.wall_stacks() == upper.wall_stacks()
    assert ground.shaft_stacks() == upper.shaft_stacks()


def test_removing_a_bearing_line_gives_exactly_one_conflict():
    ground, upper = levels()
    doomed = "V:x=12.00"
    assert doomed in upper.wall_stacks()
    upper.fabric.graph.walls = [
        w for w in upper.fabric.graph.walls if w.stack_id != doomed
    ]

    conflicts = stack_conflicts(ground, upper)
    assert len(conflicts) == 1
    only = conflicts[0]
    assert isinstance(only, Conflict)
    assert only.kind == "wall"
    assert only.stack_id == doomed
    assert only.levels == (0, 1)
    assert "level 0" in only.detail and "level 1" in only.detail


def test_a_missing_shaft_is_reported_too():
    ground, upper = levels()
    dropped = sorted(upper.shaft_stacks())[0]
    upper.shafts = [s for s in upper.shafts if s.stack_id != dropped]

    conflicts = stack_conflicts(ground, upper)
    assert [c.kind for c in conflicts] == ["shaft"]
    assert conflicts[0].stack_id == dropped


def test_conflicts_are_reported_from_both_directions():
    ground, upper = levels()
    upper.shafts = []
    ground_only = stack_conflicts(ground, upper)
    upper_only = stack_conflicts(upper, ground)

    assert len(ground_only) == len(upper_only) == 2
    assert {c.stack_id for c in ground_only} == {c.stack_id for c in upper_only}
    assert ground_only[0].levels == (0, 1)
    assert upper_only[0].levels == (1, 0)


def test_a_partition_moving_between_levels_is_not_a_conflict():
    """Only bearing walls stack. Two levels may lay their cloisons out freely."""
    ground, upper = levels()
    for wall in upper.fabric.graph.walls:
        if wall.kind is WallKind.CLOISON:
            wall.kind = WallKind.WET
    assert stack_conflicts(ground, upper) == []
