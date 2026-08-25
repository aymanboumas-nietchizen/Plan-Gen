"""L5 / L7 tests — the two checks that run inside the search loop.

Both are gates: a candidate passes or is discarded, and neither is ever traded
off in a score. Both must be cheap enough to steer the search rather than judge
it afterwards.

The reachability fixture is built by hand rather than realised from a tree,
because the failure it has to catch — a bedroom whose only door is to the
bathroom — is exactly the kind of plan a slicing tree with a spine will not
produce. It has to be constructed on purpose.
"""

from __future__ import annotations

import time

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
from planfgen.circulation import ReachabilityReport, entry_space, reachable
from planfgen.fabric import WallKind
from planfgen.habitability import FURNITURE, FurnitureSpec, fit_report, fits
from planfgen.partition import PartitionPlan, SpaceCell, StructuralGrid

P = MA_PROFILE
F, C = WallKind.FACADE, WallKind.CLOISON


def cell(nom, x, y, w, h, left, right, bottom, top) -> SpaceCell:
    return SpaceCell(
        nom, x, y, w, h,
        {"left": left, "right": right, "bottom": bottom, "top": top},
    )


def hand_built(outline, edge_kinds, rooms, cells, entry_edge=0):
    """A FabricPlan assembled from rectangles, without going through a tree."""
    programme = Programme([RoomSpec(n, k, a, "#888888") for n, k, a in rooms])
    parcel = Parcel(
        outline=Polygon(outline),
        edges=[EdgeSpec(i, k) for i, k in enumerate(edge_kinds)],
        north=0.0,
        entry_edge=entry_edge,
    )
    brief = Brief(programme, parcel, P, check_feasibility(programme, parcel, P))
    minx, miny, maxx, maxy = parcel.outline.bounds
    plan = PartitionPlan(
        cells=cells,
        grid=StructuralGrid.from_span(maxx - minx, maxy - miny),
        envelope_rect=(minx, miny, maxx - minx, maxy - miny),
        brief=brief,
    )
    return plan.to_fabric(P)


def bedroom_behind_the_bathroom():
    """An L-shaped flat where the chambre opens onto the SDB and nothing else.

    The notch is what makes it possible: three of the chambre's four sides are
    facade, so the bathroom is genuinely its only way in.
    """
    return hand_built(
        outline=[(0, 0), (8, 0), (8, 3), (4, 3), (4, 6), (0, 6)],
        edge_kinds=[
            EdgeType.STREET,
            EdgeType.MITOYEN,
            EdgeType.COURT,
            EdgeType.COURT,
            EdgeType.COURT,
            EdgeType.MITOYEN,
        ],
        rooms=[
            ("Couloir", RoomType.COULOIR, 7.0),
            ("Sejour", RoomType.SEJOUR, 14.0),
            ("SDB", RoomType.SDB, 7.0),
            ("Chambre", RoomType.CHAMBRE, 11.0),
        ],
        cells=[
            cell("Couloir", 0.0, 0.0, 1.4, 6.0, F, C, F, F),
            cell("Sejour", 1.4, 3.0, 2.6, 3.0, C, F, C, F),
            cell("SDB", 1.4, 0.0, 2.6, 3.0, C, C, F, C),
            cell("Chambre", 4.0, 0.0, 4.0, 3.0, C, F, F, F),
        ],
    )


def spine_flat():
    """A left-hand spine with three rooms opening straight onto it.

    Depths are chosen so the furniture actually fits: the sejour needs 3.00 m
    of clear width, which a 3.00 m bay does not give once its walls are taken
    off, so it gets 3.40.
    """
    return hand_built(
        outline=[(0, 0), (8, 0), (8, 9), (0, 9)],
        edge_kinds=[
            EdgeType.STREET,
            EdgeType.MITOYEN,
            EdgeType.COURT,
            EdgeType.MITOYEN,
        ],
        rooms=[
            ("Couloir", RoomType.COULOIR, 10.0),
            ("SDB", RoomType.SDB, 15.0),
            ("Chambre", RoomType.CHAMBRE, 18.0),
            ("Sejour", RoomType.SEJOUR, 20.0),
        ],
        cells=SPINE_CELLS(),
    )


def stranded_flat():
    """A cellier wedged in a corner whose every contact is under a door module.

    0.90, 0.90 and 0.80 m of shared wall: three neighbours, no way in. The WC
    beside it is reachable, but only by walking through the sejour.
    """
    return hand_built(
        outline=[(0, 0), (8, 0), (8, 9), (0, 9)],
        edge_kinds=[
            EdgeType.STREET,
            EdgeType.MITOYEN,
            EdgeType.COURT,
            EdgeType.MITOYEN,
        ],
        rooms=[
            ("Couloir", RoomType.COULOIR, 10.0),
            ("Cellier", RoomType.CELLIER, 1.0),
            ("WC", RoomType.WC, 5.0),
            ("Sejour", RoomType.SEJOUR, 50.0),
        ],
        cells=[
            cell("Couloir", 0.0, 0.0, 1.4, 9.0, F, C, F, F),
            cell("Cellier", 1.4, 0.0, 0.8, 0.9, C, C, F, C),
            cell("WC", 2.2, 0.0, 5.8, 0.9, C, F, F, C),
            cell("Sejour", 1.4, 0.9, 6.6, 8.1, C, F, C, F),
        ],
    )


def SPINE_CELLS():
    return [
        cell("Couloir", 0.0, 0.0, 1.4, 9.0, F, C, F, F),
        cell("SDB", 1.4, 0.0, 6.6, 2.6, C, F, F, C),
        cell("Chambre", 1.4, 2.6, 6.6, 3.0, C, F, C, C),
        cell("Sejour", 1.4, 5.6, 6.6, 3.4, C, F, C, F),
    ]


# --- the entry --------------------------------------------------------------


def test_the_entry_is_the_circulation_space_that_meets_the_street():
    fabric = spine_flat()
    assert entry_space(fabric).nom == "Couloir"
    assert entry_space(bedroom_behind_the_bathroom()).nom == "Couloir"


def test_an_entree_wins_over_a_corridor():
    fabric = spine_flat()
    fabric.spaces["SDB"].kind = RoomType.ENTREE
    assert entry_space(fabric).nom == "SDB"


def test_a_plan_with_no_frontage_on_the_entry_edge_is_rejected():
    fabric = spine_flat()
    for space in fabric.spaces.values():
        space.bounding = [w for w in space.bounding if not w.is_horizontal]
    with pytest.raises(ValueError, match="no way in"):
        entry_space(fabric)


# --- reachability -----------------------------------------------------------


def test_a_bedroom_reachable_only_through_the_bathroom_fails():
    """THE gate. ARCHITECTURE section 1: you entered the bedroom via the SDB."""
    fabric = bedroom_behind_the_bathroom()
    report = reachable(fabric)

    assert isinstance(report, ReachabilityReport)
    assert report.entry == "Couloir"
    assert report.through_room == {"Chambre": "SDB"}
    assert report.ok is False
    assert report.unreachable == set()
    assert report.reached == {"Couloir", "Sejour", "SDB", "Chambre"}
    assert "Chambre via SDB" in report.explain()


def test_the_chambre_really_has_only_the_one_neighbour():
    """The fixture is only worth anything if the geometry is as claimed."""
    fabric = bedroom_behind_the_bathroom()
    assert fabric.adjacency_graph()["Chambre"] == ["SDB"]
    assert fabric.shared_wall_length("Chambre", "SDB") == pytest.approx(3.0, abs=1e-9)
    assert fabric.shared_wall_length("Chambre", "Couloir") == 0.0
    assert fabric.shared_wall_length("Chambre", "Sejour") == 0.0


def test_a_spine_every_room_opens_onto_passes():
    fabric = spine_flat()
    report = reachable(fabric)

    assert report.ok is True
    assert report.through_room == {}
    assert report.unreachable == set()
    assert report.reached == set(fabric.spaces)
    for nom in ("SDB", "Chambre", "Sejour"):
        assert fabric.shared_wall_length("Couloir", nom) >= P.door_module


def test_a_room_with_no_door_capable_wall_is_unreachable():
    fabric = stranded_flat()
    report = reachable(fabric)

    assert report.unreachable == {"Cellier"}
    assert "Cellier" not in report.reached
    assert report.ok is False
    assert "unreachable: Cellier" in report.explain()


def test_both_failures_are_reported_at_once():
    """The cellier is stranded and the WC is only reachable through the sejour."""
    report = reachable(stranded_flat())
    assert report.unreachable == {"Cellier"}
    assert report.through_room == {"WC": "Sejour"}
    assert report.ok is False


def test_contact_shorter_than_a_door_is_not_a_way_through():
    """The cellier touches three rooms and opens onto none of them."""
    fabric = stranded_flat()
    assert P.door_module == pytest.approx(1.00)

    for neighbour, run in (("Couloir", 0.9), ("WC", 0.9), ("Sejour", 0.8)):
        assert fabric.shared_wall_length("Cellier", neighbour) == pytest.approx(
            run, abs=1e-9
        )
        assert fabric.door_capable("Cellier", neighbour) is False
    assert fabric.adjacency_graph()["Cellier"] == []


# --- furniture --------------------------------------------------------------


def test_fits_rejects_the_v1_chambre_and_accepts_a_real_one():
    """1.30 x 1.75 is the largest rectangle inside v1's 11.25 m2 Chambre 2."""
    spec = FURNITURE[RoomType.CHAMBRE]
    assert (spec.min_side, spec.min_long) == (2.40, 2.70)

    assert fits(_Room(1.30, 1.75), spec) is False
    assert fits(_Room(2.50, 3.10), spec) is True
    # Orientation must not matter.
    assert fits(_Room(3.10, 2.50), spec) is True
    # Long enough but too narrow, and wide enough but too short.
    assert fits(_Room(2.30, 9.00), spec) is False
    assert fits(_Room(2.60, 2.60), spec) is False


class _Room:
    """The smallest thing `fits` needs: something with net dimensions."""

    def __init__(self, w: float, h: float):
        self._dims = (w, h)

    def net_dims(self):
        return self._dims


def test_every_furniture_spec_is_a_rectangle_with_a_note():
    for kind, spec in FURNITURE.items():
        assert isinstance(spec, FurnitureSpec)
        assert 0 < spec.min_side <= spec.min_long, kind
        assert spec.note


def test_fit_report_covers_a_fabric_plan_and_a_partition_plan():
    fabric = spine_flat()
    report = fit_report(fabric, P)
    assert set(report) == set(fabric.spaces)
    assert report["Chambre"] is True

    # The same rooms as cells, which need the profile to work out their net.
    plan = PartitionPlan(
        cells=SPINE_CELLS(),
        grid=StructuralGrid.from_span(8.0, 9.0),
        envelope_rect=(0.0, 0.0, 8.0, 9.0),
        brief=fabric_brief(),
    )
    cell_report = fit_report(plan, P)
    assert set(cell_report) == set(report)
    assert cell_report["Chambre"] is report["Chambre"]


def fabric_brief() -> Brief:
    programme = Programme(
        [
            RoomSpec("Couloir", RoomType.COULOIR, 10.0, "#888888"),
            RoomSpec("SDB", RoomType.SDB, 15.0, "#888888"),
            RoomSpec("Chambre", RoomType.CHAMBRE, 18.0, "#888888"),
            RoomSpec("Sejour", RoomType.SEJOUR, 20.0, "#888888"),
        ]
    )
    parcel = Parcel(
        outline=Polygon([(0, 0), (8, 0), (8, 9), (0, 9)]),
        edges=[EdgeSpec(i, EdgeType.STREET) for i in range(4)],
        north=0.0,
        entry_edge=0,
    )
    return Brief(programme, parcel, P, check_feasibility(programme, parcel, P))


def test_a_room_with_no_spec_always_fits():
    fabric = spine_flat()
    fabric.spaces["SDB"].kind = RoomType.CELLIER
    assert RoomType.CELLIER not in FURNITURE
    assert fit_report(fabric, P)["SDB"] is True


def test_fits_is_o1():
    """No polygon work: 100k calls must take well under a second."""
    spec = FURNITURE[RoomType.CHAMBRE]
    room = _Room(2.50, 3.10)

    start = time.perf_counter()
    for _ in range(100_000):
        fits(room, spec)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"{elapsed:.3f}s for 100k calls"


def test_fits_on_a_real_space_is_also_cheap():
    """A Space reads its net dims off cached bounds, not off a fresh polygon."""
    space = spine_flat().spaces["Chambre"]
    spec = FURNITURE[RoomType.CHAMBRE]

    start = time.perf_counter()
    for _ in range(100_000):
        fits(space, spec)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"{elapsed:.3f}s for 100k calls"


# --- where the two placeholder tables disagree ------------------------------


def test_the_regulation_and_furniture_tables_are_audited_not_assumed():
    """Both files carry placeholder numbers written from different sources.

    This pins the disagreements that exist today. If someone corrects a value,
    this test tells them what their change did — which is the point of having
    the audit at all. It does not decide who is right.
    """
    from planfgen.habitability import table_conflicts

    conflicts = {(c.kind, c.issue) for c in table_conflicts(P)}
    assert conflicts == {
        (RoomType.CHAMBRE, "width"),
        (RoomType.WC, "area"),
        (RoomType.WC, "width"),
    }


def test_a_wc_at_the_code_minimum_cannot_hold_its_own_furniture():
    """The one contradiction that is a contradiction, not a preference.

    min_area says a WC may be 1.20 m2. FURNITURE says the pan and its approach
    need 0.90 x 1.40 = 1.26 m2. A WC built exactly to the minimum is legal on
    area and has nowhere to put the fixture.
    """
    spec = FURNITURE[RoomType.WC]
    assert P.min_area[RoomType.WC] == 1.20
    assert spec.min_side * spec.min_long == pytest.approx(1.26)
    assert spec.min_side * spec.min_long > P.min_area[RoomType.WC]

    at_the_minimum = _Room(1.00, 1.20)  # 1.20 m2, exactly legal
    assert fits(at_the_minimum, spec) is False


def test_no_other_room_has_that_problem():
    """Only the WC. Every other minimum leaves room for its own furniture."""
    from planfgen.habitability import table_conflicts

    areas = [c.kind for c in table_conflicts(P) if c.issue == "area"]
    assert areas == [RoomType.WC]
