"""L2b tests — the ternary band cut.

ARCHITECTURE section 4: a binary cut splits a rectangle in two and the rooms
open into each other; a band cut splits it in three, and the middle is given a
clear width whose length falls out of the plan. That is why
`"Couloir": {"surface": 7}` is the wrong input — the corridor's area is a
result, measured afterwards as a coefficient.

The band walls are cloisons, so the axis width is 1.20 + 0.10 = 1.30 and the
clear width comes back out at exactly 1.20.
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
from planfgen.fabric import WallKind
from planfgen.partition import (
    BandCut,
    Cut,
    Direction,
    Leaf,
    SlicingTree,
    SpaceCell,
    StructuralGrid,
)

EXACT = 1e-9
P = MA_PROFILE


def brief_for(rooms: list[tuple[str, RoomType, float]], w: float, h: float) -> Brief:
    programme = Programme([RoomSpec(n, k, a, "#888888") for n, k, a in rooms])
    parcel = Parcel(
        outline=Polygon([(0, 0), (w, 0), (w, h), (0, h)]),
        edges=[EdgeSpec(i, EdgeType.STREET) for i in range(4)],
        north=0.0,
        entry_edge=0,
    )
    return Brief(programme, parcel, P, check_feasibility(programme, parcel, P))


def shared_run(a: SpaceCell, b: SpaceCell) -> float:
    """Metres of edge two axis rectangles hold in common."""
    over_x = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    over_y = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    if abs(over_x) < EXACT and over_y > EXACT:
        return over_y
    if abs(over_y) < EXACT and over_x > EXACT:
        return over_x
    return 0.0


def tiled_area(plan) -> float:
    """Union area of the cells — equals the sum only if nothing overlaps."""
    union = None
    for c in plan.cells:
        box = Polygon(
            [(c.x, c.y), (c.x + c.w, c.y), (c.x + c.w, c.y + c.h), (c.x, c.y + c.h)]
        )
        union = box if union is None else union.union(box)
    return union.area


# --- one band, two rooms ----------------------------------------------------

#: Totals chosen so each flanking pair asks for roughly what its rect delivers:
#: 10.00 less 0.30 of facade, 0.20 of band wall and 1.20 of clear leaves 8.30 of
#: net run against 7.70 of net rise, and 6.30 against 9.70 the other way.
SIMPLE = {
    Direction.V: (36.0, 28.0),
    Direction.H: (36.0, 25.0),
}


def simple_plan(direction: Direction):
    sejour, chambre = SIMPLE[direction]
    brief = brief_for(
        [
            ("Sejour", RoomType.SEJOUR, sejour),
            ("Chambre", RoomType.CHAMBRE, chambre),
            ("Couloir", RoomType.COULOIR, 7.0),
        ],
        10.0,
        8.0,
    )
    tree = SlicingTree(BandCut(direction, (Leaf("Sejour"), Leaf("Chambre"))))
    return tree.realise((0.0, 0.0, 10.0, 8.0), brief, StructuralGrid.from_span(10, 8))


@pytest.mark.parametrize("direction", [Direction.V, Direction.H])
def test_band_clear_width_is_exactly_the_corridor_minimum(direction: Direction):
    """THE contract of the band cut: 1.20 m of clear, in either direction."""
    plan = simple_plan(direction)
    band = plan.circulation_cells[0]

    assert band.is_band is True
    assert plan.band_clear_width(band, P) == pytest.approx(P.corridor_clear, abs=EXACT)
    assert plan.band_clear_width(band, P) == pytest.approx(1.20, abs=EXACT)

    # The axis width carries half of each cloison on top of the clear width.
    axis_width = band.w if direction is Direction.V else band.h
    assert axis_width == pytest.approx(1.20 + P.cloison_t, abs=EXACT)
    assert axis_width == pytest.approx(1.30, abs=EXACT)


@pytest.mark.parametrize("direction", [Direction.V, Direction.H])
def test_flanking_rooms_still_get_their_target_areas(direction: Direction):
    plan = simple_plan(direction)
    errors = plan.area_error(P)

    assert set(errors) == {"Sejour", "Chambre"}, "the band has no area target"
    assert plan.max_area_error(P) < 0.005


@pytest.mark.parametrize("direction", [Direction.V, Direction.H])
def test_the_three_cells_tile_the_rect_exactly(direction: Direction):
    plan = simple_plan(direction)

    assert len(plan.cells) == 3
    for cell in plan.cells:
        assert cell.w > 0 and cell.h > 0
    assert sum(c.axis_area for c in plan.cells) == pytest.approx(80.0, abs=EXACT)
    assert tiled_area(plan) == pytest.approx(80.0, abs=EXACT)


def test_band_runs_the_full_length_of_its_rect():
    """The band gets a width; its length is whatever the plan happens to give."""
    band = simple_plan(Direction.V).circulation_cells[0]
    assert band.h == pytest.approx(8.0, abs=EXACT)
    band = simple_plan(Direction.H).circulation_cells[0]
    assert band.w == pytest.approx(10.0, abs=EXACT)


def test_band_walls_are_cloisons_and_the_outer_edges_stay_facade():
    band = simple_plan(Direction.V).circulation_cells[0]
    assert band.wall_kinds["left"] is WallKind.CLOISON
    assert band.wall_kinds["right"] is WallKind.CLOISON
    assert band.wall_kinds["bottom"] is WallKind.FACADE
    assert band.wall_kinds["top"] is WallKind.FACADE


def test_the_declared_corridor_area_is_ignored():
    """Whatever the programme says the corridor needs, the band takes a width."""
    brief = brief_for(
        [
            ("Sejour", RoomType.SEJOUR, 36.0),
            ("Chambre", RoomType.CHAMBRE, 28.0),
            ("Couloir", RoomType.COULOIR, 7.0),
        ],
        10.0,
        8.0,
    )
    tree = SlicingTree(BandCut(Direction.V, (Leaf("Sejour"), Leaf("Chambre"))))
    assert tree.demand(tree.root, brief.programme) == pytest.approx(64.0, abs=EXACT)
    assert tree.leaves() == [Leaf("Sejour"), Leaf("Chambre")]
    assert len(tree.bands()) == 1


def test_a_band_is_exempt_from_the_aspect_gate():
    """A 1.20 x 8.00 corridor is 6.4:1 and that is exactly what it should be."""
    plan = simple_plan(Direction.V)
    band = plan.circulation_cells[0]
    net_w, net_h = band.net_dims(P)
    assert max(net_w, net_h) / min(net_w, net_h) > 6.0
    assert plan.aspects_ok() is True


def test_width_source_selects_the_regulation_value():
    band = BandCut(Direction.V, (Leaf("A"), Leaf("B")))
    assert band.clear_width(P) == pytest.approx(P.corridor_clear)
    pmr = BandCut(Direction.V, (Leaf("A"), Leaf("B")), width_source="pmr")
    assert pmr.clear_width(P) == pytest.approx(P.pmr_circle)
    assert pmr.axis_width(P) == pytest.approx(P.pmr_circle + P.cloison_t)
    with pytest.raises(ValueError, match="width_source"):
        BandCut(Direction.V, (Leaf("A"), Leaf("B")), width_source="nope").clear_width(P)


def test_a_tree_with_more_bands_than_circulation_rooms_is_rejected():
    brief = brief_for(
        [
            ("Sejour", RoomType.SEJOUR, 20.0),
            ("Ch1", RoomType.CHAMBRE, 14.0),
            ("Ch2", RoomType.CHAMBRE, 14.0),
            ("Couloir", RoomType.COULOIR, 7.0),
        ],
        12.0,
        10.0,
    )
    tree = SlicingTree(
        BandCut(
            Direction.V,
            (Leaf("Sejour"), BandCut(Direction.H, (Leaf("Ch1"), Leaf("Ch2")))),
        )
    )
    with pytest.raises(ValueError, match="more bands than"):
        tree.realise((0.0, 0.0, 12.0, 10.0), brief, StructuralGrid.from_span(12, 10))


# --- the circulation coefficient --------------------------------------------


def seven_room_plan():
    """Six rooms either side of a spine, plus the spine: seven in all.

    The 11.00 x 8.00 envelope delivers 9.30 of net run against 7.50 of net rise
    once the facade, the two band cloisons, the clear width and the two
    horizontal cuts per side are paid for, so the programme asks for 69.75.
    """
    brief = brief_for(
        [
            ("Sejour", RoomType.SEJOUR, 15.00),
            ("Cuisine", RoomType.CUISINE, 11.50),
            ("Ch1", RoomType.CHAMBRE_PRINCIPALE, 11.00),
            ("Ch2", RoomType.CHAMBRE, 15.05),
            ("SDB", RoomType.SDB, 8.60),
            ("WC", RoomType.WC, 8.60),
            ("Couloir", RoomType.COULOIR, 7.00),
        ],
        11.0,
        8.0,
    )
    tree = SlicingTree(
        BandCut(
            Direction.V,
            (
                Cut(
                    Direction.H,
                    False,
                    (
                        Leaf("Sejour"),
                        Cut(Direction.H, False, (Leaf("Cuisine"), Leaf("Ch1"))),
                    ),
                ),
                Cut(
                    Direction.H,
                    False,
                    (Leaf("Ch2"), Cut(Direction.H, False, (Leaf("SDB"), Leaf("WC")))),
                ),
            ),
        )
    )
    return tree.realise((0.0, 0.0, 11.0, 8.0), brief, StructuralGrid.from_span(11, 8))


def test_circulation_coefficient_of_a_seven_room_plan():
    plan = seven_room_plan()
    assert len(plan.cells) == 7
    assert [c.nom for c in plan.circulation_cells] == ["Couloir"]

    coefficient = plan.circulation_coefficient(P)
    assert 0.05 < coefficient < 0.20
    # It is a ratio of net areas, not something the programme asked for.
    band = plan.circulation_cells[0]
    assert coefficient == pytest.approx(
        band.net_area(P) / plan.total_net(P), abs=EXACT
    )


def test_the_seven_room_plan_is_a_plan_and_not_a_diagram():
    plan = seven_room_plan()
    assert plan.aspects_ok() is True
    assert sum(c.axis_area for c in plan.cells) == pytest.approx(88.0, abs=EXACT)
    assert tiled_area(plan) == pytest.approx(88.0, abs=EXACT)


# --- the T-spine ------------------------------------------------------------


def t_spine_plan():
    """A band cut nested inside one child of another — ARCHITECTURE section 4."""
    brief = brief_for(
        [
            ("Sejour", RoomType.SEJOUR, 30.0),
            ("Ch1", RoomType.CHAMBRE, 16.0),
            ("Ch2", RoomType.CHAMBRE, 16.0),
            ("Couloir", RoomType.COULOIR, 7.0),
            ("Entree", RoomType.ENTREE, 4.0),
        ],
        12.0,
        10.0,
    )
    tree = SlicingTree(
        BandCut(
            Direction.V,
            (Leaf("Sejour"), BandCut(Direction.H, (Leaf("Ch1"), Leaf("Ch2")))),
        )
    )
    return tree.realise((0.0, 0.0, 12.0, 10.0), brief, StructuralGrid.from_span(12, 10))


def test_a_nested_band_gives_two_corridors_that_meet():
    plan = t_spine_plan()
    bands = plan.circulation_cells
    assert [c.nom for c in bands] == ["Couloir", "Entree"]
    assert all(c.is_band for c in bands)

    assert shared_run(bands[0], bands[1]) > 0.0
    assert shared_run(bands[0], bands[1]) == pytest.approx(1.30, abs=EXACT)


def test_both_arms_of_the_t_keep_their_clear_width():
    plan = t_spine_plan()
    for band in plan.circulation_cells:
        assert plan.band_clear_width(band, P) == pytest.approx(1.20, abs=EXACT)


def test_the_t_spine_still_tiles_exactly():
    plan = t_spine_plan()
    assert len(plan.cells) == 5
    assert sum(c.axis_area for c in plan.cells) == pytest.approx(120.0, abs=EXACT)
    assert tiled_area(plan) == pytest.approx(120.0, abs=EXACT)
