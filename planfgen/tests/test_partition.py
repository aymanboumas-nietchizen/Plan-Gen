"""L2a tests — the grid, the slicing tree, and whether the sizing is exact.

The reference case is a 4-room tree on a 10.00 x 8.00 m envelope: a vertical cut
splitting left from right, and a horizontal cut inside each half.

The programme totals 72.96 m2, which is exactly what that envelope and that tree
can deliver: 10.00 x 8.00 less 0.30 of facade all round is 9.70 x 7.70, less one
0.10 cloison across each axis is 9.60 x 7.60. A programme that asks for what the
fabric can give is the case where "exact" means something.
"""

from __future__ import annotations

import random

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
    Cut,
    Direction,
    Leaf,
    SlicingTree,
    StructuralGrid,
    aspect_ok,
    axis_dims,
)

EXACT = 1e-9
ENVELOPE = (0.0, 0.0, 10.0, 8.0)

#: Chosen so the programme asks for exactly what the tree can deliver.
DELIVERABLE = {"A": 18.30, "B": 18.18, "C": 18.24, "D": 18.24}


def brief_for(demands: dict[str, float]) -> Brief:
    programme = Programme(
        [RoomSpec(nom, RoomType.CHAMBRE, area, "#888888") for nom, area in demands.items()]
    )
    parcel = Parcel(
        outline=Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]),
        edges=[EdgeSpec(i, EdgeType.STREET) for i in range(4)],
        north=0.0,
        entry_edge=0,
    )
    return Brief(
        programme, parcel, MA_PROFILE, check_feasibility(programme, parcel, MA_PROFILE)
    )


def four_room_tree(structural: bool) -> SlicingTree:
    """V( H(A, B), H(C, D) ) — left and right, each split bottom and top."""
    return SlicingTree(
        Cut(
            Direction.V,
            structural,
            (
                Cut(Direction.H, structural, (Leaf("A"), Leaf("B"))),
                Cut(Direction.H, structural, (Leaf("C"), Leaf("D"))),
            ),
        )
    )


def grid() -> StructuralGrid:
    return StructuralGrid.from_span(10.0, 8.0)


# --- the grid ---------------------------------------------------------------


def test_from_span_takes_the_coarsest_module_under_the_limit():
    g = grid()
    assert (g.module_x, g.module_y) == (5.0, 4.0)
    assert StructuralGrid.from_span(12.0, 12.0).module_x == 4.0
    assert StructuralGrid.from_span(10.5, 10.5).module_x == 3.5
    # A span already inside the limit is one bay.
    assert StructuralGrid.from_span(4.0, 4.0).module_x == 4.0


def test_snap_and_lines():
    g = grid()
    assert g.snap(4.3618, "y") == 4.0
    assert g.snap(4.9381, "x") == 5.0
    assert g.snap(6.1, "y") == 8.0
    assert g.lines_x(0.0, 10.0) == [0.0, 5.0, 10.0]
    assert g.lines_y(0.0, 8.0) == [0.0, 4.0, 8.0]
    assert g.lines_y(0.5, 7.5) == [4.0]
    with pytest.raises(ValueError, match="expected 'x' or 'y'"):
        g.snap(1.0, "z")


# --- the net/gross inversion ------------------------------------------------


def test_axis_dims_round_trips_to_the_requested_net_area():
    """Feed the output back through the net formula of ARCHITECTURE section 2."""
    rng = random.Random(20260824)
    for _ in range(20):
        net_area = rng.uniform(3.0, 40.0)
        aspect = rng.uniform(0.4, 2.5)
        t_left, t_right, t_bottom, t_top = (
            rng.choice([0.10, 0.20, 0.30]) for _ in range(4)
        )
        w, h = axis_dims(net_area, aspect, t_left, t_right, t_bottom, t_top)
        back = (w - (t_left + t_right) / 2) * (h - (t_bottom + t_top) / 2)
        assert back == pytest.approx(net_area, abs=EXACT)


def test_axis_dims_honours_the_requested_aspect():
    w, h = axis_dims(12.0, 1.5, 0.10, 0.10, 0.10, 0.10)
    assert (w - 0.10) / (h - 0.10) == pytest.approx(1.5, abs=EXACT)


def test_axis_dims_rejects_nonsense():
    with pytest.raises(ValueError, match="net_area"):
        axis_dims(0.0, 1.0, 0.1, 0.1, 0.1, 0.1)
    with pytest.raises(ValueError, match="aspect"):
        axis_dims(10.0, 0.0, 0.1, 0.1, 0.1, 0.1)


# --- the tree ---------------------------------------------------------------


def test_leaves_and_demand():
    tree = four_room_tree(structural=False)
    programme = brief_for(DELIVERABLE).programme
    assert [leaf.nom for leaf in tree.leaves()] == ["A", "B", "C", "D"]
    assert tree.demand(tree.root, programme) == pytest.approx(72.96, abs=EXACT)
    left = tree.root.children[0]
    assert tree.demand(left, programme) == pytest.approx(18.30 + 18.18, abs=EXACT)


def test_from_sequence_is_balanced_and_reproducible():
    a = SlicingTree.from_sequence(["A", "B", "C", "D"], seed=3)
    assert [leaf.nom for leaf in a.leaves()] == ["A", "B", "C", "D"]
    assert a == SlicingTree.from_sequence(["A", "B", "C", "D"], seed=3)
    assert SlicingTree.from_sequence(["A"], seed=3).root == Leaf("A")
    with pytest.raises(ValueError, match="at least one room"):
        SlicingTree.from_sequence([], seed=3)


def test_cut_wall_kind_follows_structural():
    assert Cut(Direction.V, True, (Leaf("A"), Leaf("B"))).wall_kind is WallKind.PORTEUR
    assert Cut(Direction.V, False, (Leaf("A"), Leaf("B"))).wall_kind is WallKind.CLOISON


# --- realising the tree -----------------------------------------------------


def test_free_cuts_give_every_room_its_exact_net_area():
    """A cloison is free, so the leaves come out exact — ARCHITECTURE section 5."""
    brief = brief_for(DELIVERABLE)
    plan = four_room_tree(structural=False).realise(ENVELOPE, brief, grid())

    assert plan.max_area_error(MA_PROFILE) < 0.005
    for nom, error in plan.area_error(MA_PROFILE).items():
        assert error == pytest.approx(0.0, abs=EXACT), nom
    assert plan.total_net(MA_PROFILE) == pytest.approx(72.96, abs=EXACT)


def test_free_cuts_stay_exact_however_uneven_the_programme():
    """Each cut pays for its own wall before dividing, so depth does not drift."""
    brief = brief_for({"A": 24.0, "B": 14.0, "C": 20.0, "D": 14.96})
    plan = four_room_tree(structural=False).realise(ENVELOPE, brief, grid())
    assert plan.max_area_error(MA_PROFILE) == pytest.approx(0.0, abs=EXACT)


def test_structural_cuts_absorb_the_grid_tolerance():
    """The same tree, snapped to a 5.00 x 4.00 grid and walled in porteurs."""
    brief = brief_for(DELIVERABLE)
    plan = four_room_tree(structural=True).realise(ENVELOPE, brief, grid())

    assert plan.max_area_error(MA_PROFILE) < 0.03
    # Every cut sits on a grid line, and every cell is one full bay.
    for cell in plan.cells:
        assert (cell.w, cell.h) == pytest.approx((5.0, 4.0), abs=EXACT)
    assert plan.total_net(MA_PROFILE) == pytest.approx(4 * 4.75 * 3.75, abs=EXACT)


def test_structural_cuts_land_on_grid_lines_even_when_demand_does_not():
    """The free cut wants y = 4.0125; the structural one is pulled to 4.00."""
    brief = brief_for(DELIVERABLE)
    free = four_room_tree(structural=False).realise(ENVELOPE, brief, grid())
    snapped = four_room_tree(structural=True).realise(ENVELOPE, brief, grid())

    free_a = next(c for c in free.cells if c.nom == "A")
    snapped_a = next(c for c in snapped.cells if c.nom == "A")
    assert free_a.h == pytest.approx(4.0125, abs=EXACT)
    assert snapped_a.h == pytest.approx(4.0, abs=EXACT)

    lines_x, lines_y = grid().lines_x(0, 10), grid().lines_y(0, 8)
    for cell in snapped.cells:
        assert any(abs(cell.x + cell.w - v) < EXACT for v in lines_x)
        assert any(abs(cell.y + cell.h - v) < EXACT for v in lines_y)


def test_outer_edges_are_facade_and_internal_edges_follow_the_cut():
    brief = brief_for(DELIVERABLE)
    plan = four_room_tree(structural=False).realise(ENVELOPE, brief, grid())
    cell_a = next(c for c in plan.cells if c.nom == "A")  # lower left
    assert cell_a.wall_kinds == {
        "left": WallKind.FACADE,
        "bottom": WallKind.FACADE,
        "right": WallKind.CLOISON,
        "top": WallKind.CLOISON,
    }
    structural = four_room_tree(structural=True).realise(ENVELOPE, brief, grid())
    cell_a = next(c for c in structural.cells if c.nom == "A")
    assert cell_a.wall_kinds["right"] is WallKind.PORTEUR
    assert cell_a.wall_kinds["left"] is WallKind.FACADE


# --- the tiling -------------------------------------------------------------


@pytest.mark.parametrize("structural", [False, True])
def test_cells_tile_the_envelope_exactly(structural: bool):
    """Positive rectangles, no gap and no overlap."""
    brief = brief_for(DELIVERABLE)
    plan = four_room_tree(structural).realise(ENVELOPE, brief, grid())

    assert len(plan.cells) == 4
    for cell in plan.cells:
        assert cell.w > 0 and cell.h > 0
        assert 0.0 <= cell.x and cell.x + cell.w <= 10.0 + EXACT
        assert 0.0 <= cell.y and cell.y + cell.h <= 8.0 + EXACT

    assert sum(c.axis_area for c in plan.cells) == pytest.approx(80.0, abs=EXACT)
    union = None
    for cell in plan.cells:
        box = Polygon(
            [
                (cell.x, cell.y),
                (cell.x + cell.w, cell.y),
                (cell.x + cell.w, cell.y + cell.h),
                (cell.x, cell.y + cell.h),
            ]
        )
        union = box if union is None else union.union(box)
    assert union.area == pytest.approx(80.0, abs=EXACT)


def test_net_total_is_always_less_than_the_axis_total():
    brief = brief_for(DELIVERABLE)
    plan = four_room_tree(structural=False).realise(ENVELOPE, brief, grid())
    assert plan.total_net(MA_PROFILE) < sum(c.axis_area for c in plan.cells)


# --- the aspect gate --------------------------------------------------------


def test_aspect_ok_is_a_ratio_on_the_net_dimensions():
    assert aspect_ok(6.0, 1.0) is False
    assert aspect_ok(2.5, 1.0) is True
    assert aspect_ok(1.0, 2.5) is True
    assert aspect_ok(0.0, 1.0) is False


def test_aspects_ok_is_false_for_a_tree_forced_into_a_slot():
    """A tiny demand beside a large one gives a full-height 7:1 slot."""
    brief = brief_for({"Couloir": 8.0, "Sejour": 64.0})
    tree = SlicingTree(Cut(Direction.V, False, (Leaf("Couloir"), Leaf("Sejour"))))
    plan = tree.realise(ENVELOPE, brief, grid())

    slot = next(c for c in plan.cells if c.nom == "Couloir")
    net_w, net_h = slot.net_dims(MA_PROFILE)
    assert max(net_w, net_h) / min(net_w, net_h) > 6.0
    assert plan.aspects_ok() is False


def test_aspects_ok_is_true_for_the_reference_plan():
    brief = brief_for(DELIVERABLE)
    assert four_room_tree(structural=False).realise(ENVELOPE, brief, grid()).aspects_ok()

# --- unbalanced trees -------------------------------------------------------


def lopsided_tree() -> SlicingTree:
    """Leaves at depths 3, 3, 2 and 1 — as unbalanced as four rooms get."""
    return SlicingTree(
        Cut(
            Direction.V,
            False,
            (
                Cut(
                    Direction.H,
                    False,
                    (
                        Leaf("A"),
                        Cut(Direction.H, False, (Leaf("B"), Leaf("C"))),
                    ),
                ),
                Leaf("D"),
            ),
        )
    )


def test_one_pass_drifts_when_the_tree_is_unbalanced():
    """The failure refinement exists to fix: shallow leaves over, deep under.

    A cut pays for its own wall and divides what is left, but cannot know that
    one side will spend more on walls below it than the other.
    """
    brief = brief_for({"A": 18.0, "B": 15.0, "C": 12.0, "D": 27.72})
    plan = lopsided_tree().realise(ENVELOPE, brief, grid(), refine=0)

    assert plan.max_area_error(MA_PROFILE) > 0.01
    errors = plan.area_error(MA_PROFILE)
    assert errors["D"] > 0 > errors["B"], "the shallow leaf gains what the deep ones lose"


def test_refinement_makes_an_unbalanced_tree_exact():
    brief = brief_for({"A": 18.0, "B": 15.0, "C": 12.0, "D": 27.72})
    plan = lopsided_tree().realise(ENVELOPE, brief, grid())

    assert plan.max_area_error(MA_PROFILE) < 1e-9
    assert sum(c.axis_area for c in plan.cells) == pytest.approx(80.0, abs=EXACT)


def test_refinement_only_redistributes_it_does_not_invent_area():
    """When the envelope cannot deliver, every room should be short equally."""
    brief = brief_for({"A": 25.0, "B": 22.0, "C": 23.0, "D": 20.0})  # 90 vs 72.96
    plan = four_room_tree(structural=False).realise(ENVELOPE, brief, grid())

    errors = plan.area_error(MA_PROFILE)
    assert max(errors.values()) - min(errors.values()) < 1e-9
    assert all(e < 0 for e in errors.values())


def test_refinement_leaves_an_unbalanced_shortfall_uniform():
    brief = brief_for({"A": 20.0, "B": 14.0, "C": 10.0, "D": 28.0})  # 72 vs ~72.7
    one = lopsided_tree().realise(ENVELOPE, brief, grid(), refine=0)
    many = lopsided_tree().realise(ENVELOPE, brief, grid())

    def spread(plan):
        e = plan.area_error(MA_PROFILE)
        return max(e.values()) - min(e.values())

    assert spread(one) > 0.03
    assert spread(many) < 1e-9
    assert many.max_area_error(MA_PROFILE) < one.max_area_error(MA_PROFILE)


def test_refinement_never_degrades_a_snapped_plan():
    """A structural cut is pinned to the grid; refinement must not fight it."""
    brief = brief_for(DELIVERABLE)
    one = four_room_tree(structural=True).realise(ENVELOPE, brief, grid(), refine=0)
    many = four_room_tree(structural=True).realise(ENVELOPE, brief, grid())

    assert many.max_area_error(MA_PROFILE) <= one.max_area_error(MA_PROFILE) + EXACT
    for cell in many.cells:
        assert (cell.w, cell.h) == pytest.approx((5.0, 4.0), abs=EXACT)


def test_a_balanced_tree_needs_no_refinement():
    brief = brief_for(DELIVERABLE)
    one = four_room_tree(structural=False).realise(ENVELOPE, brief, grid(), refine=0)
    assert one.max_area_error(MA_PROFILE) == pytest.approx(0.0, abs=EXACT)



# --- at scale ---------------------------------------------------------------


def villa_targets() -> dict[str, float]:
    """Thirteen rooms, calibrated so the tree below delivers them exactly."""
    return {
        "A": 42.0, "B": 24.0, "C": 17.0, "D": 7.0, "E": 22.0, "F": 15.0,
        "G": 15.0, "H": 13.0, "I": 9.0, "J": 8.0, "K": 4.0, "L": 13.0, "M": 8.0,
    }


def _chain(direction: Direction, noms: list[str]):
    node = Leaf(noms[-1])
    for nom in reversed(noms[:-1]):
        node = Cut(direction, False, (Leaf(nom), node))
    return node


def _nest(direction: Direction, noms: list[str]):
    if len(noms) == 1:
        return Leaf(noms[0])
    half = len(noms) // 2
    other = Direction.V if direction is Direction.H else Direction.H
    return Cut(direction, False, (_nest(other, noms[:half]), _nest(other, noms[half:])))


def _depth(node, d: int = 0) -> int:
    if isinstance(node, Leaf):
        return d
    return max(_depth(child, d + 1) for child in node.children)


def _calibrate(tree: SlicingTree, targets: dict[str, float], rounds: int = 8):
    """Rescale every leaf's target until the tree delivers it.

    Filtered by what the tree PLACES, not by room kind — a circulation room
    standing as a leaf has a real target, and only a band has none.
    """
    placed = {leaf.nom for leaf in tree.leaves()}
    working = dict(targets)
    for _ in range(rounds):
        brief = brief_for(working)
        plan = tree.realise(ENVELOPE_BIG, brief, GRID_BIG)
        got = sum(c.net_area(MA_PROFILE) for c in plan.cells if not c.is_band)
        asked = sum(v for nom, v in working.items() if nom in placed)
        if abs(got / asked - 1) < 1e-12:
            break
        scale = got / asked
        working = {n: (v * scale if n in placed else v) for n, v in working.items()}
    return brief_for(working)


ENVELOPE_BIG = (0.15, 0.15, 27.7, 23.7)
GRID_BIG = StructuralGrid.from_span(28.0, 24.0)


@pytest.mark.parametrize("shape", ["chain", "balanced"])
def test_exact_sizing_holds_at_thirteen_rooms(shape: str):
    """Everything else here is four rooms. Depth must not degrade the refinement.

    Measured: a depth-12 chain and a depth-4 nest over the same thirteen rooms
    both reach 0.00000000%. The chain needs more passes to get there, which is
    what `REFINE_PASSES` is for.
    """
    noms = list(villa_targets())
    build = _chain if shape == "chain" else _nest
    tree = SlicingTree(build(Direction.H, noms))
    assert len(tree.leaves()) == 13
    assert _depth(tree.root) == (12 if shape == "chain" else 4)

    brief = _calibrate(tree, villa_targets())
    plan = tree.realise(ENVELOPE_BIG, brief, GRID_BIG)

    assert plan.max_area_error(MA_PROFILE) == pytest.approx(0.0, abs=1e-9)
    assert sum(c.axis_area for c in plan.cells) == pytest.approx(
        27.7 * 23.7, abs=1e-6
    ), "thirteen cells still tile the envelope"


def test_a_deep_tree_needs_more_refinement_passes_than_a_shallow_one():
    """The single pass is far worse on a chain, and both converge."""
    noms = list(villa_targets())
    chain_tree = SlicingTree(_chain(Direction.H, noms))
    brief = _calibrate(chain_tree, villa_targets())

    once = chain_tree.realise(ENVELOPE_BIG, brief, GRID_BIG, refine=0)
    many = chain_tree.realise(ENVELOPE_BIG, brief, GRID_BIG)

    assert once.max_area_error(MA_PROFILE) > 0.01, "one pass is several percent out"
    assert many.max_area_error(MA_PROFILE) < 1e-9
