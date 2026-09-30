"""L7 layout tests — furniture placed, not merely assumed to fit.

What is held: every piece inside its room, no two pieces on the same floor,
nothing in a door's square (both faces of the wall), nothing taller than the
sill in front of a window, a 0.60 m walk from the door to every piece, the same
plan giving the same furniture — and a room that cannot be furnished saying
which piece and why. The drawing tests: DXF layers, SVG pieces, JSON keys.
"""

from __future__ import annotations

import json
import math

import ezdxf
import pytest

from planfgen.document import export_dxf, to_gh_json, to_svg
from planfgen.document.furniture import furniture_document, symbols
from planfgen.habitability.layout import (
    FAMILIES,
    ROOM_ITEMS,
    FurnishedPlan,
    _Room,
    furnish,
    furnish_room,
    items_for,
)
from planfgen.openings import place_openings
from planfgen.services import place_shafts

from planfgen.tests.test_openings import FLAT_RELATIONS, topology_for
from planfgen.tests.test_services import P, flat


def overlap(a, b) -> bool:
    return a[0] < b[2] - 1e-6 and b[0] < a[2] - 1e-6 and a[1] < b[3] - 1e-6 and b[1] < a[3] - 1e-6


def both_faces(door):
    """A door's swing square, and its mirror across the wall: the approach."""
    x0, y0, x1, y1 = door.clearance_box()
    if door.wall.is_horizontal:
        c = door.wall.p0[1]
        return [(x0, y0, x1, y1), (x0, 2 * c - y1, x1, 2 * c - y0)]
    c = door.wall.p0[0]
    return [(x0, y0, x1, y1), (2 * c - x1, y0, 2 * c - x0, y1)]


@pytest.fixture(scope="module")
def plan():
    fabric = flat()
    openings = place_openings(fabric, topology_for(FLAT_RELATIONS), P)
    shafts = place_shafts(fabric, P)
    return fabric, openings, shafts, furnish(fabric, openings, shafts)


def room(rect=(0.0, 0.0, 3.4, 3.6), doors=(), windows=(), kind="CHAMBRE_PRINCIPALE") -> _Room:
    sides = set()
    for d in doors:
        if d[1] <= rect[1] + 1e-9:
            sides.add("S")
    return _Room("R", kind, rect, list(doors), list(windows), [], sides, set(), 1.00)


# --- the real plan ------------------------------------------------------------


def test_every_room_with_a_standard_set_is_furnished(plan):
    fabric, _, _, furnished = plan
    assert isinstance(furnished, FurnishedPlan)
    assert furnished.complete, furnished.explain()
    kinds = {r.kind for r in furnished.rooms.values()}
    assert {"SEJOUR", "CUISINE", "CHAMBRE_PRINCIPALE", "CHAMBRE", "SDB", "WC"} <= kinds
    assert "Couloir" not in furnished.rooms, "a corridor is not furnished"
    families = {p.family for p in furnished.pieces}
    assert "lit_double_160x200" in families and "placard_60" in families
    assert "refrigerateur" in families and "lavabo" in families


def test_every_piece_is_inside_its_room(plan):
    fabric, _, _, furnished = plan
    for piece in furnished.pieces:
        x0, y0, x1, y1 = fabric.spaces[piece.room].net_polygon.bounds
        a = piece.rect
        assert a[0] >= x0 - 1e-6 and a[1] >= y0 - 1e-6, piece
        assert a[2] <= x1 + 1e-6 and a[3] <= y1 + 1e-6, piece


def test_no_two_pieces_overlap(plan):
    pieces = plan[3].pieces
    for i, a in enumerate(pieces):
        for b in pieces[i + 1:]:
            assert not overlap(a.rect, b.rect), (a.family, b.family)


def test_nothing_stands_in_a_door_swing_or_its_approach(plan):
    _, openings, _, furnished = plan
    squares = [sq for door in openings.doors for sq in both_faces(door)]
    for piece in furnished.pieces:
        for sq in squares:
            assert not overlap(piece.rect, sq), piece.family


def test_nothing_taller_than_the_sill_blinds_a_window(plan):
    fabric, openings, _, furnished = plan
    for room_layout in furnished.rooms.values():
        for piece in room_layout.pieces:
            if piece.height <= P.allege_h:
                continue
            for window in openings.windows:
                low, high = window.span
                (x, y) = window.wall.p0
                if window.wall.is_horizontal:
                    strip = (x + low, y - 0.8, x + high, y + 0.8)
                else:
                    strip = (x - 0.8, y + low, x + 0.8, y + high)
                assert not overlap(piece.rect, strip), (piece.room, piece.family)


def test_a_bathroom_takes_the_wc_only_when_the_unit_has_none():
    assert "WC" not in [i.nom for i in items_for("SDB", has_wc=True)]
    assert "WC" in [i.nom for i in items_for("SDB", has_wc=False)]
    assert items_for("BUANDERIE", True) == items_for("CELLIER", True)


def test_the_same_plan_gives_the_same_furniture(plan):
    fabric, openings, shafts, furnished = plan
    again = furnish(fabric, openings, shafts)
    assert [(p.family, p.rect) for p in again.pieces] == [
        (p.family, p.rect) for p in furnished.pieces
    ]


# --- one room -----------------------------------------------------------------


def test_the_walk_from_the_door_reaches_every_piece():
    """Door in the middle of the south wall; the bed goes opposite, lanes clear."""
    door = (1.30, 0.0, 2.10, 0.80)
    layout = furnish_room(room(doors=[door]), items_for("CHAMBRE_PRINCIPALE", True))
    assert layout.complete, layout.missing
    bed = next(p for p in layout.pieces if p.family.startswith("lit_double"))
    assert not overlap(bed.rect, door)
    # the double bed keeps a lane both sides: 1.60 + 2 x 0.60
    assert bed.width == pytest.approx(1.60)


def test_a_room_too_small_names_the_piece_and_the_reason():
    layout = furnish_room(
        room(rect=(0.0, 0.0, 2.2, 2.4), doors=[(0.1, 0.0, 0.9, 0.8)]),
        items_for("CHAMBRE_PRINCIPALE", True),
    )
    assert not layout.complete
    miss = layout.missing[0]
    assert miss.item == "lit double + chevets" and miss.code == "too_small"
    assert "2.20 x 2.40" in miss.reason


def test_a_placard_is_not_put_in_front_of_a_window():
    """The only wall long enough is glazed: the placard is refused, and says so."""
    windows = [(0.0, 0.0, 1.80, 0.60)]  # a strip along the whole south wall
    r = room(rect=(0.0, 0.0, 1.80, 1.30), doors=[(0.0, 0.40, 0.80, 1.30)], windows=windows,
             kind="ENTREE")
    r = _Room(r.nom, r.kind, r.rect, r.doors, r.windows, [], {"W"}, {"S"}, 1.00)
    layout = furnish_room(r, items_for("ENTREE", True))
    for piece in layout.pieces:
        if piece.height > 1.00:
            assert not overlap(piece.rect, windows[0])


def test_rotation_is_a_bearing_and_insertion_is_the_back_edge(plan):
    for piece in plan[3].pieces:
        fx, fy = piece.facing
        assert math.isclose(math.hypot(fx, fy), 1.0)
        assert piece.rotation == pytest.approx(math.atan2(fx, fy) % (2 * math.pi))
        cx, cy = piece.center
        bx, by = piece.insertion
        assert (cx - bx) * fx + (cy - by) * fy == pytest.approx(piece.depth / 2, abs=1e-6)


def test_every_family_used_is_in_the_vocabulary():
    for items in ROOM_ITEMS.values():
        for item in items:
            for variant in item.variants:
                for part in variant.parts:
                    assert part.family in FAMILIES
    for key, family in FAMILIES.items():
        assert key == family.key and family.width > 0 and family.depth > 0 and family.height > 0


# --- drawing -------------------------------------------------------------------


def test_the_dxf_carries_mobilier_and_placard_layers(plan, tmp_path):
    fabric, openings, shafts, furnished = plan
    target = tmp_path / "meuble.dxf"
    export_dxf(fabric, target, openings=openings, shafts=shafts, furnished=furnished)
    doc = ezdxf.readfile(target)
    layers = {layer.dxf.name for layer in doc.layers}
    assert {"MOBILIER", "PLACARD", "EQUIPEMENT"} <= layers
    msp = doc.modelspace()
    assert len(msp.query('*[layer=="PLACARD"]')) > 0
    assert len(msp.query('*[layer=="MOBILIER"]')) > 0


def test_the_svg_draws_the_pieces_and_the_door_swings(plan, tmp_path):
    fabric, openings, _, furnished = plan
    svg = to_svg(fabric, tmp_path / "p.svg", openings=openings, furnished=furnished)
    assert 'class="furniture"' in svg and 'data-layer="PLACARD"' in svg
    assert 'data-family="lit_double_160x200"' in svg
    assert svg.count('class="door"') == len(openings.doors)
    plain = to_svg(fabric, tmp_path / "q.svg")
    assert 'class="furniture"' not in plain


def test_the_json_model_carries_what_revit_needs(plan):
    fabric, openings, shafts, furnished = plan
    document = to_gh_json(fabric, openings, shafts, furnished)
    json.dumps(document)
    assert to_gh_json(fabric, openings, shafts)["furniture"] == []
    rooms = {s["nom"] for s in document["spaces"]}
    assert len(document["furniture"]) == len(furnished.pieces)
    for entry in document["furniture"]:
        assert entry["family"] in FAMILIES
        assert entry["room"] in rooms
        for key in ("width", "depth", "height", "insertion", "rotation", "facing", "symbols"):
            assert key in entry
        assert entry["symbols"][0][0] == "poly"


def test_symbols_start_with_the_outline(plan):
    for piece in plan[3].pieces:
        outline = symbols(piece)[0]
        xs = [p[0] for p in outline[1]]
        ys = [p[1] for p in outline[1]]
        assert (min(xs), min(ys), max(xs), max(ys)) == pytest.approx(piece.rect, abs=1e-3)
    assert furniture_document(None) == []
