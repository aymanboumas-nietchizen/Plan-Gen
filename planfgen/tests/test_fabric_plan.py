"""L3b tests — the net/gross closed form, and adjacency that can host a door.

The reference case is the S2 fixture given real thicknesses: FACADE 0.30 on the
four outer edges of the 6.00 x 4.00 rectangle, CLOISON 0.10 on the two internal
cuts at x = 3.00 and y = 2.00.
"""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from planfgen.brief import MA_PROFILE, EdgeSpec, EdgeType, Parcel, RoomType
from planfgen.fabric import (
    FabricPlan,
    Space,
    WallAxis,
    WallGraph,
    WallKind,
    net_polygon,
    wall_solids,
)

EXACT = 1e-9


def parcel_6x4() -> Parcel:
    return Parcel(
        outline=Polygon([(0, 0), (6, 0), (6, 4), (0, 4)]),
        edges=[EdgeSpec(i, EdgeType.STREET) for i in range(4)],
        north=0.0,
        entry_edge=0,
    )


def build(walls, named, parcel=None) -> FabricPlan:
    """Node a hand-built graph and name its faces by centroid.

    `named` is a list of (nom, kind, cx, cy). S6 will build these from a
    partition; here they are placed by hand so L3b can be tested alone.
    """
    graph = WallGraph()
    for p0, p1, kind in walls:
        graph.add(WallAxis(p0, p1, kind))
    graph.split_at_crossings()
    faces = graph.faces()

    spaces = {}
    for nom, kind, cx, cy in named:
        face = next(
            f
            for f in faces
            if abs(f.centroid.x - cx) < 1e-6 and abs(f.centroid.y - cy) < 1e-6
        )
        bounding = graph.bounding_walls(face)
        spaces[nom] = Space(
            nom=nom,
            kind=kind,
            axis_polygon=face,
            net_polygon=net_polygon(face, bounding, MA_PROFILE),
            bounding=bounding,
        )
    return FabricPlan(graph, spaces, parcel or parcel_6x4(), MA_PROFILE)


GRID_WALLS = [
    ((0, 0), (6, 0), WallKind.FACADE),
    ((0, 4), (6, 4), WallKind.FACADE),
    ((0, 0), (0, 4), WallKind.FACADE),
    ((6, 0), (6, 4), WallKind.FACADE),
    ((3, 0), (3, 4), WallKind.CLOISON),
    ((0, 2), (6, 2), WallKind.CLOISON),
]

GRID_CELLS = [
    ("Sud-Ouest", RoomType.SEJOUR, 1.5, 1.0),
    ("Sud-Est", RoomType.CUISINE, 4.5, 1.0),
    ("Nord-Ouest", RoomType.CHAMBRE, 1.5, 3.0),
    ("Nord-Est", RoomType.CHAMBRE, 4.5, 3.0),
]


def grid_plan() -> FabricPlan:
    return build(GRID_WALLS, GRID_CELLS)


def square_plan(kind: WallKind, size: float = 3.0) -> FabricPlan:
    """One `size` x `size` axis cell bounded by four walls of a single kind."""
    walls = [
        ((0, 0), (size, 0), kind),
        ((0, size), (size, size), kind),
        ((0, 0), (0, size), kind),
        ((size, 0), (size, size), kind),
    ]
    parcel = Parcel(
        outline=Polygon([(0, 0), (size, 0), (size, size), (0, size)]),
        edges=[EdgeSpec(i, EdgeType.STREET) for i in range(4)],
        north=0.0,
        entry_edge=0,
    )
    half = size / 2
    return build(walls, [("Cellule", RoomType.CHAMBRE, half, half)], parcel)


# --- the closed form --------------------------------------------------------


def test_grid_cell_net_area_matches_the_closed_form():
    """Half of each bounding wall, computed literally: FACADE 0.30, CLOISON 0.10."""
    expected = (3.00 - 0.30 / 2 - 0.10 / 2) * (2.00 - 0.30 / 2 - 0.10 / 2)
    cell = grid_plan().spaces["Sud-Ouest"]
    assert cell.surface_utile == pytest.approx(expected, abs=EXACT)


def test_net_and_axis_dims_differ_by_half_of_each_wall():
    cell = grid_plan().spaces["Sud-Ouest"]
    assert cell.axis_dims() == pytest.approx((3.0, 2.0), abs=EXACT)
    assert cell.net_dims() == pytest.approx((2.80, 1.80), abs=EXACT)


def test_three_metre_cell_loses_more_to_bearing_walls_than_to_partitions():
    """ARCHITECTURE section 2: 8.41 behind cloisons, 7.84 behind porteurs.

    That is 6.6% and 12.9% below a nominal 9.00 m2 — the difference between a
    compliant 9 m2 chambre and a non-compliant one.
    """
    cloison = square_plan(WallKind.CLOISON).spaces["Cellule"]
    porteur = square_plan(WallKind.PORTEUR).spaces["Cellule"]

    assert cloison.surface_utile == pytest.approx(8.41, abs=EXACT)
    assert porteur.surface_utile == pytest.approx(7.84, abs=EXACT)
    assert cloison.net_dims() == pytest.approx((2.90, 2.90), abs=EXACT)
    assert porteur.net_dims() == pytest.approx((2.80, 2.80), abs=EXACT)

    minimum = MA_PROFILE.min_area[RoomType.CHAMBRE]
    assert cloison.surface_utile < minimum and porteur.surface_utile < minimum


def test_net_polygon_is_inset_not_rounded():
    """Four corners, square. A Shapely negative buffer would not give this."""
    net = square_plan(WallKind.CLOISON).spaces["Cellule"].net_polygon
    assert len(net.exterior.coords) - 1 == 4
    assert net.bounds == pytest.approx((0.05, 0.05, 2.95, 2.95), abs=EXACT)


def test_wall_solids_are_length_by_thickness_on_the_axis():
    plan = grid_plan()
    solids = {id(w): p for w, p in wall_solids(plan.graph, MA_PROFILE)}
    assert len(solids) == 12
    bottom = next(
        w for w in plan.graph.walls if (w.p0, w.p1) == ((0.0, 0.0), (3.0, 0.0))
    )
    assert solids[id(bottom)].bounds == pytest.approx(
        (0.0, -0.15, 3.0, 0.15), abs=EXACT
    )
    assert solids[id(bottom)].area == pytest.approx(3.0 * 0.30, abs=EXACT)


# --- adjacency that can host a door -----------------------------------------


def test_door_capable_at_two_metres_but_not_at_sixty_three_centimetres():
    """The door module is a 0.80 leaf plus two 0.10 jambs, so 1.00 m."""
    assert MA_PROFILE.door_module == pytest.approx(1.00)

    plan = build(
        [
            ((0, 0), (6, 0), WallKind.FACADE),
            ((0, 4), (6, 4), WallKind.FACADE),
            ((0, 0), (0, 4), WallKind.FACADE),
            ((6, 0), (6, 4), WallKind.FACADE),
            ((3, 0), (3, 4), WallKind.CLOISON),
            ((0, 0.63), (3, 0.63), WallKind.CLOISON),
        ],
        [
            ("Placard", RoomType.CELLIER, 1.5, 0.315),
            ("Chambre", RoomType.CHAMBRE, 1.5, 2.315),
            ("Sejour", RoomType.SEJOUR, 4.5, 2.0),
        ],
    )
    # The placard touches the sejour along only its own 0.63 m of the x=3 wall.
    assert plan.shared_wall_length("Placard", "Sejour") == pytest.approx(
        0.63, abs=EXACT
    )
    assert plan.door_capable("Placard", "Sejour") is False

    assert plan.shared_wall_length("Chambre", "Sejour") == pytest.approx(
        3.37, abs=EXACT
    )
    assert plan.door_capable("Chambre", "Sejour") is True

    assert plan.shared_wall_length("Placard", "Chambre") == pytest.approx(
        3.00, abs=EXACT
    )
    assert plan.door_capable("Placard", "Chambre") is True


def test_shared_wall_length_on_the_grid():
    plan = grid_plan()
    assert plan.shared_wall_length("Sud-Ouest", "Sud-Est") == pytest.approx(
        2.0, abs=EXACT
    )
    assert plan.shared_wall_length("Sud-Ouest", "Nord-Ouest") == pytest.approx(
        3.0, abs=EXACT
    )
    assert plan.shared_wall_length("Sud-Ouest", "Nord-Est") == 0.0
    assert plan.door_capable("Sud-Ouest", "Nord-Est") is False


def test_adjacency_graph_gives_each_cell_two_neighbours():
    adjacency = grid_plan().adjacency_graph()
    assert {nom: sorted(n) for nom, n in adjacency.items()} == {
        "Sud-Ouest": ["Nord-Ouest", "Sud-Est"],
        "Sud-Est": ["Nord-Est", "Sud-Ouest"],
        "Nord-Ouest": ["Nord-Est", "Sud-Ouest"],
        "Nord-Est": ["Nord-Ouest", "Sud-Est"],
    }


# --- the plan as a whole ----------------------------------------------------


def test_total_utile_sums_the_delivered_net_areas():
    plan = grid_plan()
    cell = (3.00 - 0.30 / 2 - 0.10 / 2) * (2.00 - 0.30 / 2 - 0.10 / 2)
    assert plan.total_utile == pytest.approx(4 * cell, abs=EXACT)
    # The fabric always delivers less than the axis grid promises.
    assert plan.total_utile < sum(s.axis_polygon.area for s in plan.spaces.values())


def test_exterior_walls_are_the_ones_on_the_parcel_outline():
    plan = grid_plan()
    exterior = plan.exterior_walls(plan.spaces["Sud-Ouest"])
    assert len(exterior) == 2
    assert {(w.p0, w.p1) for w in exterior} == {
        ((0.0, 0.0), (3.0, 0.0)),
        ((0.0, 0.0), (0.0, 2.0)),
    }
    assert all(w.kind is WallKind.FACADE for w in exterior)
