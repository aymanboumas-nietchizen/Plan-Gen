"""The architect's decisions of 2026-09-29: CELLIER becomes BUANDERIE, a wet
room served beside the SDB or off the kitchen; the entree's door is a decision.

What is pinned here: old briefs still load; the laundry is wet, needs no
daylight, takes a 0.83 m leaf; and it may be reached THROUGH the kitchen — the
one (room, via) pair `PASS_THROUGH` allows — while every other through-room
stays refused.
"""

from __future__ import annotations

import pytest

from planfgen.brief import EdgeType, Programme, RoomType
from planfgen.brief.regulation import PROFILES
from planfgen.circulation import PASS_THROUGH, reachable
from planfgen.habitability import FURNITURE
from planfgen.openings import DAYLIGHT_KINDS
from planfgen.tests.test_gates import C, F, cell, hand_built


def test_old_briefs_with_a_cellier_load_as_a_buanderie():
    assert RoomType("cellier") is RoomType.BUANDERIE
    assert RoomType("buanderie") is RoomType.BUANDERIE
    assert RoomType.from_name("CELLIER") is RoomType.BUANDERIE
    assert RoomType.from_name("SDB") is RoomType.SDB
    programme = Programme.from_json({"programme": [
        {"nom": "Cellier", "kind": "CELLIER", "surface_utile": 3.0, "couleur": "#aaaaaa"},
    ]})
    assert programme.rooms[0].kind is RoomType.BUANDERIE
    assert "CELLIER" not in RoomType.__members__
    with pytest.raises(KeyError):
        RoomType.from_name("GARAGE")


def test_the_buanderie_is_wet_and_needs_no_daylight():
    assert RoomType.BUANDERIE.is_wet
    assert RoomType.BUANDERIE not in DAYLIGHT_KINDS
    spec = FURNITURE[RoomType.BUANDERIE]
    assert (spec.min_side, spec.min_long) == (1.20, 1.60)
    assert "washing machine" in spec.note


@pytest.mark.parametrize("name", sorted(PROFILES))
def test_door_sizes_of_2026_09_29(name):
    """BUANDERIE 0.83 leaf, 0.93 module; ENTREE a 1.00 m module, written down."""
    profile = PROFILES[name]
    assert profile.door_leaf_for(RoomType.BUANDERIE) == pytest.approx(0.83)
    assert profile.door_module_for(RoomType.BUANDERIE) == pytest.approx(0.93)
    assert RoomType.ENTREE in profile.door_leaf_by_kind
    assert profile.door_module_for(RoomType.ENTREE) == pytest.approx(1.00)
    assert profile.door_module_for(RoomType.ENTREE) == pytest.approx(profile.door_module)
    # unlisted kinds keep today's behaviour
    assert profile.door_module_for(RoomType.TERRASSE) == pytest.approx(profile.door_module)


def laundry_flat(third: RoomType = RoomType.BUANDERIE, second: RoomType = RoomType.CUISINE):
    """A spine; the kitchen and the sejour off it; a third room in the corner
    that touches the kitchen and the sejour but not the corridor."""
    return hand_built(
        outline=[(0, 0), (8, 0), (8, 8), (0, 8)],
        edge_kinds=[EdgeType.STREET, EdgeType.MITOYEN, EdgeType.COURT, EdgeType.MITOYEN],
        rooms=[
            ("Couloir", RoomType.COULOIR, 10.0),
            ("Sejour", RoomType.SEJOUR, 30.0),
            ("Cuisine", second, 10.0),
            ("Buanderie", third, 6.0),
        ],
        cells=[
            cell("Couloir", 0.0, 0.0, 1.4, 8.0, F, C, F, F),
            cell("Sejour", 1.4, 3.0, 6.6, 5.0, C, F, C, F),
            cell("Cuisine", 1.4, 0.0, 4.0, 3.0, C, C, F, C),
            cell("Buanderie", 5.4, 0.0, 2.6, 3.0, C, F, F, C),
        ],
    )


def test_a_buanderie_off_the_kitchen_is_legal():
    fabric = laundry_flat()
    assert fabric.shared_wall_length("Buanderie", "Couloir") == 0.0
    assert fabric.door_capable("Buanderie", "Cuisine")
    report = reachable(fabric)
    assert report.ok, report.explain()


def test_only_that_pair_is_relaxed():
    """The same corner as a WC is still a room reached through a room; a
    buanderie whose only neighbours are a chambre and the sejour is too."""
    as_wc = reachable(laundry_flat(third=RoomType.WC))
    assert not as_wc.ok and "Buanderie" in as_wc.through_room
    off_a_bedroom = reachable(laundry_flat(second=RoomType.CHAMBRE))
    assert not off_a_bedroom.ok and "Buanderie" in off_a_bedroom.through_room
    assert PASS_THROUGH == frozenset({(RoomType.BUANDERIE, RoomType.CUISINE)})


def test_the_pass_through_is_one_hop():
    """A room behind the buanderie is not reached 'through the kitchen'."""
    fabric = hand_built(
        outline=[(0, 0), (10, 0), (10, 8), (0, 8)],
        edge_kinds=[EdgeType.STREET, EdgeType.MITOYEN, EdgeType.COURT, EdgeType.MITOYEN],
        rooms=[
            ("Couloir", RoomType.COULOIR, 10.0),
            ("Sejour", RoomType.SEJOUR, 30.0),
            ("Cuisine", RoomType.CUISINE, 10.0),
            ("Buanderie", RoomType.BUANDERIE, 6.0),
            ("Other", RoomType.BUANDERIE, 6.0),
        ],
        cells=[
            cell("Couloir", 0.0, 0.0, 1.4, 8.0, F, C, F, F),
            cell("Sejour", 1.4, 3.0, 8.6, 5.0, C, F, C, F),
            cell("Cuisine", 1.4, 0.0, 4.0, 3.0, C, C, F, C),
            cell("Buanderie", 5.4, 0.0, 2.3, 3.0, C, C, F, C),
            cell("Other", 7.7, 0.0, 2.3, 3.0, C, F, F, C),
        ],
    )
    report = reachable(fabric)
    assert "Buanderie" not in report.through_room
    assert report.through_room.get("Other") in ("Buanderie", "Sejour")


def test_the_door_between_kitchen_and_laundry_is_a_0_83_leaf():
    from types import SimpleNamespace

    from planfgen.openings import place_doors
    from planfgen.topology import ProgrammeGraph, Relation, RelationType

    fabric = laundry_flat()
    graph = ProgrammeGraph([Relation("Cuisine", "Buanderie", RelationType.CONNECTED, 1.0)])
    report = place_doors(fabric, SimpleNamespace(graph=graph), PROFILES["placeholder"])
    leaves = [d.leaf for d in report.doors if d.swing_into in ("Cuisine", "Buanderie")]
    assert leaves == [pytest.approx(0.83)]

