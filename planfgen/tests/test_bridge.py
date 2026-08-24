"""L2 -> L3 tests — the crossing where rooms stop being authored.

A `SpaceCell` is a rectangle the slicing tree placed. A `Space` is a face of the
wall graph. They are different objects arrived at by different routes, and the
round trip is only worth anything because both measure their net area from the
same walls. If the two ever disagree, one of the two layers is lying.

The reference case is a five-space apartment on 11.00 x 8.00 m: a vertical spine
with two rooms either side. The tree is realised on the outline inset by half the
facade, so the facade solids land exactly inside the parcel boundary.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

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
from planfgen.document.preview import PALETTE, to_svg
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
ROUND_TRIP = 1e-6
W, H = 11.0, 8.0
P = MA_PROFILE

#: Totals 65.70 for the four rooms, which is what 9.00 x 7.30 of net delivers
#: once the spine and the two horizontal cuts are paid for.
ROOMS = [
    ("Sejour", RoomType.SEJOUR, 26.0),
    ("Cuisine", RoomType.CUISINE, 12.0),
    ("Chambre", RoomType.CHAMBRE_PRINCIPALE, 19.0),
    ("SDB", RoomType.SDB, 8.7),
    ("Couloir", RoomType.COULOIR, 8.0),
]


def five_room_brief() -> Brief:
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
    return Brief(programme, parcel, P, check_feasibility(programme, parcel, P))


def five_room_partition():
    brief = five_room_brief()
    tree = SlicingTree(
        BandCut(
            Direction.V,
            (
                Cut(Direction.H, False, (Leaf("Sejour"), Leaf("Cuisine"))),
                Cut(Direction.H, False, (Leaf("Chambre"), Leaf("SDB"))),
            ),
        )
    )
    inset = P.facade_t / 2
    envelope = (inset, inset, W - 2 * inset, H - 2 * inset)
    return tree.realise(envelope, brief, StructuralGrid.from_span(W, H))


# --- the round trip ---------------------------------------------------------


def test_every_space_matches_the_cell_it_came_from():
    """THE bridge contract: the fabric measures what the partition promised."""
    plan = five_room_partition()
    fabric = plan.to_fabric(P)

    assert len(fabric.spaces) == len(plan.cells) == 5
    for cell in plan.cells:
        space = fabric.spaces[cell.nom]
        assert space.surface_utile == pytest.approx(
            cell.net_area(P), abs=ROUND_TRIP
        ), cell.nom
        assert space.axis_polygon.area == pytest.approx(cell.axis_area, abs=ROUND_TRIP)


def test_the_partition_delivered_what_the_programme_asked_for():
    """Not a bridge property, but the reason the bridge is worth crossing."""
    plan = five_room_partition()
    fabric = plan.to_fabric(P)
    programme = plan.brief.programme

    for nom, space in fabric.spaces.items():
        if space.kind.is_circulation:
            continue
        assert space.surface_utile == pytest.approx(
            programme.by_nom(nom).surface_utile, abs=1e-6
        ), nom


def test_spaces_keep_the_kinds_the_programme_gave_them():
    fabric = five_room_partition().to_fabric(P)
    assert fabric.spaces["Couloir"].kind is RoomType.COULOIR
    assert fabric.spaces["Chambre"].kind is RoomType.CHAMBRE_PRINCIPALE
    assert [s.nom for s in fabric.spaces.values() if s.kind.is_wet] == ["Cuisine", "SDB"]


# --- the wall graph ---------------------------------------------------------


def test_no_axis_is_authored_twice():
    """An edge two cells share is one wall. Two would double its thickness."""
    graph = five_room_partition().to_wall_graph(P)
    counts = Counter((wall.p0, wall.p1) for wall in graph.walls)
    assert [key for key, n in counts.items() if n > 1] == []

    graph.split_at_crossings()
    counts = Counter((wall.p0, wall.p1) for wall in graph.walls)
    assert [key for key, n in counts.items() if n > 1] == []


def test_only_the_envelope_carries_facade():
    """Every axis on the inset boundary is facade; every interior axis is not.

    The outer runs come back subdivided — the bottom line is cut where the
    sejour, the corridor and the chambre meet it — which is the point: the
    graph is already noded along each line before it is ever crossed.
    """
    graph = five_room_partition().to_wall_graph(P)
    inset = P.facade_t / 2
    edges = {inset, W - inset}, {inset, H - inset}

    facade_run = 0.0
    for wall in graph.walls:
        fixed = wall.p0[1] if wall.is_horizontal else wall.p0[0]
        limits = edges[1] if wall.is_horizontal else edges[0]
        on_boundary = any(abs(fixed - v) < EXACT for v in limits)
        assert (wall.kind is WallKind.FACADE) == on_boundary, wall
        if on_boundary:
            facade_run += wall.length

    perimeter = 2 * ((W - 2 * inset) + (H - 2 * inset))
    assert facade_run == pytest.approx(perimeter, abs=EXACT)


def test_where_two_cells_disagree_the_thicker_wall_wins():
    """Neither room may be given a thinner wall than its neighbour believes."""
    from planfgen.partition.bridge import wall_axes

    left = SpaceCell(
        "left", 0.0, 0.0, 3.0, 3.0,
        {"left": WallKind.FACADE, "right": WallKind.CLOISON,
         "bottom": WallKind.FACADE, "top": WallKind.FACADE},
    )
    right = SpaceCell(
        "right", 3.0, 0.0, 3.0, 3.0,
        {"left": WallKind.PORTEUR, "right": WallKind.FACADE,
         "bottom": WallKind.FACADE, "top": WallKind.FACADE},
    )
    axes = wall_axes([left, right], P)
    shared = [w for w in axes if w.is_vertical and abs(w.p0[0] - 3.0) < EXACT]

    assert len(shared) == 1, "one wall, not one per room"
    assert shared[0].kind is WallKind.PORTEUR
    assert (shared[0].p0, shared[0].p1) == ((3.0, 0.0), (3.0, 3.0))
    assert P.thickness_of("porteur") > P.thickness_of("cloison")
    # The two bottom edges are collinear neighbours, not the same wall.
    bottoms = [w for w in axes if w.is_horizontal and abs(w.p0[1]) < EXACT]
    assert len(bottoms) == 2 and all(w.kind is WallKind.FACADE for w in bottoms)


def test_each_rectangular_space_is_bounded_by_four_walls():
    """Four, unless a neighbour T-joins the edge and splits it — see below."""
    fabric = five_room_partition().to_fabric(P)
    for nom in ("Sejour", "Cuisine", "Chambre", "SDB"):
        assert len(fabric.spaces[nom].bounding) == 4, nom


def test_the_corridor_is_bounded_by_more_walls_than_it_has_sides():
    """Its long sides are cut where the rooms either side meet them.

    Still four *lines* — the extra axes are collinear pieces of the same two
    runs, which is why the net polygon comes back a clean rectangle.
    """
    fabric = five_room_partition().to_fabric(P)
    corridor = fabric.spaces["Couloir"]

    assert len(corridor.bounding) == 6
    lines = {
        (wall.is_horizontal, round(wall.p0[1] if wall.is_horizontal else wall.p0[0], 9))
        for wall in corridor.bounding
    }
    assert len(lines) == 4
    assert len(corridor.net_polygon.exterior.coords) - 1 == 4


def test_the_corridor_reaches_every_room():
    """The v1 failure this whole rewrite exists to avoid.

    ARCHITECTURE section 1: in v1 the only way into Chambre 1 was through the
    bathroom. Here every room opens onto the spine and nothing else is needed.
    """
    fabric = five_room_partition().to_fabric(P)
    adjacency = fabric.adjacency_graph()

    assert sorted(adjacency["Couloir"]) == ["Chambre", "Cuisine", "SDB", "Sejour"]
    for nom in ("Sejour", "Cuisine", "Chambre", "SDB"):
        assert "Couloir" in adjacency[nom], nom


# --- the drawing ------------------------------------------------------------


def test_to_svg_writes_one_fill_per_space(tmp_path: Path):
    fabric = five_room_partition().to_fabric(P)
    target = tmp_path / "preview.svg"
    svg = to_svg(fabric, target)

    assert target.exists()
    assert svg == target.read_text(encoding="utf-8")
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")

    for space in fabric.spaces.values():
        colour = PALETTE[space.kind]
        assert f'fill="{colour}" fill-opacity="0.30"' in svg
    # One fill per space, one outline for the parcel, one arrow, plus the walls.
    assert svg.count("<polygon") == len(fabric.spaces) + 2 + len(fabric.graph.walls)


def test_to_svg_stamps_the_rooms(tmp_path: Path):
    fabric = five_room_partition().to_fabric(P)
    svg = to_svg(fabric, tmp_path / "preview.svg")

    for nom, space in fabric.spaces.items():
        assert f">{nom}<" in svg
        assert f">{space.surface_utile:.2f} m²<" in svg
    assert ">N<" in svg, "north arrow"
    assert "m</text>" in svg, "scale bar"


def test_to_svg_show_selects_what_is_stamped(tmp_path: Path):
    fabric = five_room_partition().to_fabric(P)
    svg = to_svg(fabric, tmp_path / "names.svg", show=("nom",))

    assert ">Sejour<" in svg
    assert "m²<" not in svg
    assert "×" not in svg
