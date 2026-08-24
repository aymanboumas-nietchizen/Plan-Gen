"""L0 tests — orientation, edge legality, the partition estimate and the gate."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from planfgen.brief import (
    MA_PROFILE,
    Brief,
    EdgeSpec,
    EdgeType,
    InfeasibleBrief,
    Orientation,
    Parcel,
    Programme,
    RoomSpec,
    RoomType,
    estimate_partition_length,
)

FIXTURES = Path(__file__).parent / "fixtures"


def square_parcel(north: float = 0.0, kinds: list[EdgeType] | None = None) -> Parcel:
    """A 12 x 9 CCW rectangle, four STREET edges unless told otherwise.

    Ring order is bottom, right, top, left — so with north along +Y the edges
    face S, E, N, O in that order.
    """
    kinds = kinds or [EdgeType.STREET] * 4
    return Parcel(
        outline=Polygon([(0, 0), (12, 0), (12, 9), (0, 9)]),
        edges=[EdgeSpec(i, k) for i, k in enumerate(kinds)],
        north=north,
        entry_edge=0,
    )


# --- orientation ------------------------------------------------------------


def test_orientation_with_north_along_y():
    parcel = square_parcel(north=0.0)
    facing = [parcel.orientation_of(i) for i in range(4)]
    assert facing == [Orientation.S, Orientation.E, Orientation.N, Orientation.O]


def test_orientation_with_north_along_x():
    """north = pi/2 puts true north on +X, rotating every edge one sector."""
    parcel = square_parcel(north=math.pi / 2)
    facing = [parcel.orientation_of(i) for i in range(4)]
    assert facing == [Orientation.E, Orientation.N, Orientation.O, Orientation.S]


def test_orientation_is_indifferent_to_ring_winding():
    """A CW ring must still report outward normals, not inward ones."""
    cw = Parcel(
        outline=Polygon([(0, 0), (0, 9), (12, 9), (12, 0)]),
        edges=[EdgeSpec(i, EdgeType.STREET) for i in range(4)],
        north=0.0,
        entry_edge=0,
    )
    assert [cw.orientation_of(i) for i in range(4)] == [
        Orientation.O,
        Orientation.N,
        Orientation.E,
        Orientation.S,
    ]


# --- edge legality ----------------------------------------------------------


def test_mitoyen_is_not_openable_but_street_is():
    parcel = square_parcel(
        kinds=[EdgeType.STREET, EdgeType.MITOYEN, EdgeType.RETRAIT, EdgeType.GARDEN]
    )
    assert parcel.openable(0) is True
    assert parcel.openable(1) is False
    assert parcel.openable(2) is False
    assert parcel.openable(3) is True


def test_entry_on_mitoyen_edge_is_rejected():
    with pytest.raises(ValueError, match="STREET or GARDEN"):
        Parcel(
            outline=Polygon([(0, 0), (12, 0), (12, 9), (0, 9)]),
            edges=[EdgeSpec(i, EdgeType.MITOYEN) for i in range(4)],
            north=0.0,
            entry_edge=0,
        )


def test_entry_on_garden_edge_is_accepted():
    kinds = [EdgeType.GARDEN, EdgeType.MITOYEN, EdgeType.MITOYEN, EdgeType.MITOYEN]
    assert square_parcel(kinds=kinds).entry_edge == 0


def test_edge_count_must_match_the_outline():
    with pytest.raises(ValueError, match="4 outline segments but 3"):
        Parcel(
            outline=Polygon([(0, 0), (12, 0), (12, 9), (0, 9)]),
            edges=[EdgeSpec(i, EdgeType.STREET) for i in range(3)],
            north=0.0,
            entry_edge=0,
        )


# --- programme accessors ----------------------------------------------------


def test_room_type_classification():
    assert RoomType.CUISINE.is_wet and RoomType.SDB.is_wet and RoomType.WC.is_wet
    assert not RoomType.SEJOUR.is_wet
    assert RoomType.COULOIR.is_circulation and RoomType.ENTREE.is_circulation
    assert not RoomType.CHAMBRE.is_circulation


def test_by_nom_finds_the_room_or_raises():
    programme = Programme(
        rooms=[
            RoomSpec("Séjour", RoomType.SEJOUR, 30.0, "#4a9eff"),
            RoomSpec("WC", RoomType.WC, 5.0, "#fb923c", daylight=False),
        ]
    )
    assert programme.by_nom("WC").surface_utile == 5.0
    assert programme.total_utile == pytest.approx(35.0)
    with pytest.raises(KeyError):
        programme.by_nom("Cellier")


# --- the partition estimate -------------------------------------------------


def test_partition_length_matches_the_calibration():
    """ARCHITECTURE section 3 calibrates 7 rooms over 95.76 m2 at 33.66 m."""
    estimate = estimate_partition_length(7, 95.76)
    assert estimate == pytest.approx(33.66, rel=0.01)


# --- the feasibility gate ---------------------------------------------------

#: The v1 fixture names rooms but does not type them. "Chambre 1" is the larger
#: of the two, so it reads as the chambre principale.
V1_KIND = {
    "Séjour": RoomType.SEJOUR,
    "Cuisine": RoomType.CUISINE,
    "Chambre 1": RoomType.CHAMBRE_PRINCIPALE,
    "Chambre 2": RoomType.CHAMBRE,
    "SDB": RoomType.SDB,
    "WC": RoomType.WC,
    "Couloir": RoomType.COULOIR,
}


def adapt_v1_fixture(fixture: dict) -> dict:
    """Wrap a v1 brief in the v2 shape.

    v1 knew only a width and a height, so the envelope becomes a rectangle with
    four STREET edges and north along +Y — the most permissive parcel there is,
    which makes the gate's verdict a property of the programme alone. It also
    used `surface` for the net area and `facade` for the daylight requirement.
    """
    w = fixture["envelope"]["W"]
    h = fixture["envelope"]["H"]
    return {
        "programme": [
            {
                "nom": room["nom"],
                "kind": V1_KIND[room["nom"]].name,
                "surface_utile": float(room["surface"]),
                "couleur": room["couleur"],
                "daylight": bool(room.get("facade", True)),
            }
            for room in fixture["programme"]
        ],
        "parcel": {
            "outline": [[0, 0], [w, 0], [w, h], [0, h]],
            "edges": [{"index": i, "kind": "STREET"} for i in range(4)],
            "north": 0.0,
            "entry_edge": 0,
        },
    }


@pytest.fixture
def v1_brief_path(tmp_path: Path) -> Path:
    source = json.loads(
        (FIXTURES / "apartment_7rooms.json").read_text(encoding="utf-8")
    )
    target = tmp_path / "apartment_7rooms_v2.json"
    target.write_text(
        json.dumps(adapt_v1_fixture(source), ensure_ascii=False), encoding="utf-8"
    )
    return target


def test_v1_apartment_is_infeasible(v1_brief_path: Path):
    """The 7-room brief on its 12 x 9 envelope cannot be built at any thickness.

    ARCHITECTURE section 1 measures the shortfall at 10.6 m2: 103 m2 programmed
    against 92.39 m2 habitable once the facade and an estimated 33.66 m of
    cloison are charged. Assert on the deficit, not on the message.
    """
    with pytest.raises(InfeasibleBrief) as excinfo:
        Brief.load(v1_brief_path)

    budget = excinfo.value.budget
    assert not budget.ok
    assert 10.0 < budget.deficit < 11.5
    assert budget.required == pytest.approx(103.0)
    assert budget.interior == pytest.approx(95.76)


def test_infeasible_budget_explains_itself(v1_brief_path: Path):
    with pytest.raises(InfeasibleBrief) as excinfo:
        Brief.load(v1_brief_path)
    line = excinfo.value.budget.explain()
    assert "DEFICIT" in line
    assert "\n" not in line


def test_a_smaller_programme_on_the_same_parcel_loads(tmp_path: Path):
    """The gate must pass what fits, or it is not a gate."""
    source = json.loads(
        (FIXTURES / "apartment_7rooms.json").read_text(encoding="utf-8")
    )
    data = adapt_v1_fixture(source)
    for room in data["programme"]:
        room["surface_utile"] *= 0.8
    target = tmp_path / "smaller.json"
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    brief = Brief.load(target)
    assert brief.budget.ok
    assert brief.profile is MA_PROFILE
    assert brief.programme.total_utile == pytest.approx(82.4)
    assert [r.nom for r in brief.programme.circulation_rooms] == ["Couloir"]
