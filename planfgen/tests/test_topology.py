"""L1 tests — typed relations, the access gradient, and the leaf ordering.

The v1 fixture is still loadable, which is the point of the untyped-pair path:
old briefs are promoted to CONNECTED rather than rejected. But an untyped pair
list is also all v1 could express, and the gradient test below shows what that
costs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from planfgen.brief import Programme, RoomSpec, RoomType
from planfgen.topology import (
    ProgrammeGraph,
    Relation,
    RelationType,
    TopologyPlan,
    Zone,
    access_gradient,
    day_night,
    depths,
    suggest_tree_order,
    wet_cluster,
)

FIXTURES = Path(__file__).parent / "fixtures"
R = RelationType


def v1_fixture() -> dict:
    return json.loads(
        (FIXTURES / "apartment_7rooms.json").read_text(encoding="utf-8")
    )


def apartment_programme() -> Programme:
    """The seven-room flat, with an entrance hall the v1 brief never had."""
    rooms = [
        ("Entrée", RoomType.ENTREE, 4.0),
        ("Séjour", RoomType.SEJOUR, 30.0),
        ("Cuisine", RoomType.CUISINE, 12.0),
        ("Couloir", RoomType.COULOIR, 7.0),
        ("Chambre 1", RoomType.CHAMBRE_PRINCIPALE, 16.0),
        ("Chambre 2", RoomType.CHAMBRE, 12.0),
        ("SDB", RoomType.SDB, 6.0),
        ("WC", RoomType.WC, 3.0),
    ]
    return Programme([RoomSpec(n, k, a, "#888888") for n, k, a in rooms])


def apartment_graph() -> ProgrammeGraph:
    """A typed graph: doors, one wet wall, and one thing kept apart.

    You enter the sejour; the couloir hangs off it and serves the night zone.
    That one extra step is what puts the chambres at depth 3 — hang the couloir
    straight off the entrance instead and they come back SEMI.
    """
    return ProgrammeGraph(
        [
            Relation("Entrée", "Séjour", R.CONNECTED),
            Relation("Entrée", "WC", R.CONNECTED),
            Relation("Séjour", "Cuisine", R.CONNECTED),
            Relation("Séjour", "Couloir", R.CONNECTED),
            Relation("Couloir", "Chambre 1", R.CONNECTED),
            Relation("Couloir", "Chambre 2", R.CONNECTED),
            Relation("Couloir", "SDB", R.CONNECTED),
            Relation("Cuisine", "SDB", R.ADJACENT, weight=2.0),
            Relation("WC", "Cuisine", R.SEPARATED),
        ]
    )


# --- relations --------------------------------------------------------------


def test_the_v1_pair_list_loads_as_nine_connected_relations():
    graph = ProgrammeGraph.from_json(v1_fixture()["adjacencies"])

    assert len(graph.relations) == 9
    assert all(r.kind is R.CONNECTED for r in graph.relations)
    assert all(r.weight == 1.0 for r in graph.relations)
    assert len(graph.noms) == 7
    assert "Séjour" in graph.noms


def test_relations_are_symmetric_and_stored_canonically():
    """Written either way round, it is the same relation."""
    one = Relation("WC", "Cuisine", R.SEPARATED)
    other = Relation("Cuisine", "WC", R.SEPARATED)

    assert one == other
    assert one.pair == ("Cuisine", "WC")
    assert one.other("WC") == "Cuisine"
    assert one.other("Cuisine") == "WC"
    with pytest.raises(KeyError):
        one.other("SDB")
    with pytest.raises(ValueError, match="cannot be related to itself"):
        Relation("WC", "WC", R.NEAR)


def test_a_separated_relation_is_retrievable_and_distinct():
    """SEPARATED is not a weak CONNECTED. It is the opposite instruction."""
    graph = apartment_graph()
    relation = graph.between("WC", "Cuisine")

    assert relation is not None
    assert relation.kind is R.SEPARATED
    assert relation.kind is not R.CONNECTED
    assert relation.kind.forbids_wall and not relation.kind.needs_wall
    assert graph.neighbours("WC", R.SEPARATED) == ["Cuisine"]
    assert "Cuisine" not in graph.neighbours("WC", R.CONNECTED)
    assert graph.neighbours("WC") == ["Cuisine", "Entrée"]


def test_relation_kinds_say_what_they_demand():
    assert R.CONNECTED.needs_wall and R.CONNECTED.needs_door
    assert R.ADJACENT.needs_wall and not R.ADJACENT.needs_door
    assert not R.NEAR.needs_wall and not R.NEAR.forbids_wall
    assert R.SEPARATED.forbids_wall


def test_to_networkx_carries_kind_and_weight():
    graph = apartment_graph().to_networkx()

    assert graph.number_of_nodes() == 8
    assert graph.number_of_edges() == 9
    assert graph["Cuisine"]["SDB"]["kind"] is R.ADJACENT
    assert graph["Cuisine"]["SDB"]["weight"] == 2.0


def test_validate_reports_names_the_programme_does_not_have():
    programme = apartment_programme()
    assert apartment_graph().validate(programme) == []

    stray = ProgrammeGraph([Relation("Séjour", "Garage", R.CONNECTED)])
    assert stray.validate(programme) == ["Garage"]


def test_relations_round_trip_through_json():
    graph = apartment_graph()
    assert ProgrammeGraph.from_json(graph.to_json()) == graph


# --- the access gradient ----------------------------------------------------


def test_chambres_are_private_and_the_sejour_is_not():
    gradient = access_gradient(apartment_graph(), "Entrée")

    assert gradient["Chambre 1"] is Zone.PRIVATE
    assert gradient["Chambre 2"] is Zone.PRIVATE
    assert gradient["Séjour"] in (Zone.PUBLIC, Zone.SEMI)
    assert gradient["Entrée"] is Zone.PUBLIC
    assert depths(apartment_graph(), "Entrée")["Chambre 1"] == 3


def test_a_flat_with_no_entrance_hall_has_no_gradient_depth():
    """What the v1 brief costs: nothing is more than two steps in.

    Every room hangs off the sejour or the couloir, so the chambres land at
    depth 2 and come back SEMI. The gradient is only as good as the graph.
    """
    graph = ProgrammeGraph.from_json(v1_fixture()["adjacencies"])
    gradient = access_gradient(graph, "Séjour")

    assert max(depths(graph, "Séjour").values()) == 2
    assert gradient["Chambre 1"] is Zone.SEMI
    assert gradient["Chambre 2"] is Zone.SEMI


def test_only_connected_relations_are_walkable():
    """A wet wall is a wall. You cannot get to the SDB through the cuisine."""
    graph = ProgrammeGraph(
        [
            Relation("Entrée", "Cuisine", R.CONNECTED),
            Relation("Cuisine", "SDB", R.ADJACENT),
        ]
    )
    assert depths(graph, "Entrée") == {"Entrée": 0, "Cuisine": 1}
    assert access_gradient(graph, "Entrée")["SDB"] is Zone.PRIVATE


def test_zone_thresholds():
    from planfgen.topology import zone_of

    assert [zone_of(d) for d in (0, 1)] == [Zone.PUBLIC, Zone.PUBLIC]
    assert zone_of(2) is Zone.SEMI
    assert [zone_of(d) for d in (3, 9)] == [Zone.PRIVATE, Zone.PRIVATE]


# --- zoning and the leaf order ----------------------------------------------


def test_wet_cluster_and_day_night():
    programme = apartment_programme()
    assert wet_cluster(programme) == ["Cuisine", "SDB", "WC"]

    zones = day_night(programme)
    assert zones["Séjour"] == "day" and zones["Cuisine"] == "day"
    assert zones["Chambre 1"] == "night" and zones["SDB"] == "night"
    assert zones["WC"] == "service" and zones["Couloir"] == "service"


def test_suggest_tree_order_keeps_the_wet_cluster_contiguous():
    """THE ordering contract: L4 cannot stack shafts that are strewn about."""
    programme = apartment_programme()
    order = suggest_tree_order(apartment_graph(), programme)

    assert sorted(order) == sorted(r.nom for r in programme.rooms)
    positions = sorted(order.index(nom) for nom in wet_cluster(programme))
    assert positions == list(range(positions[0], positions[0] + len(positions)))


def test_the_order_is_deterministic():
    programme, graph = apartment_programme(), apartment_graph()
    assert suggest_tree_order(graph, programme) == suggest_tree_order(graph, programme)


def test_separated_rooms_are_pushed_apart():
    """A SEPARATED pair should not end up side by side if anything else can."""
    programme = Programme(
        [
            RoomSpec("Séjour", RoomType.SEJOUR, 30.0, "#888888"),
            RoomSpec("Chambre", RoomType.CHAMBRE, 12.0, "#888888"),
            RoomSpec("Bureau", RoomType.BUREAU, 10.0, "#888888"),
        ]
    )
    graph = ProgrammeGraph(
        [
            Relation("Séjour", "Bureau", R.CONNECTED),
            Relation("Bureau", "Chambre", R.CONNECTED),
            Relation("Séjour", "Chambre", R.SEPARATED),
        ]
    )
    order = suggest_tree_order(graph, programme)
    assert abs(order.index("Séjour") - order.index("Chambre")) > 1


def test_an_empty_programme_orders_to_nothing():
    assert suggest_tree_order(ProgrammeGraph(), Programme([])) == []


# --- the plan ---------------------------------------------------------------


def test_topology_plan_builds_and_round_trips():
    plan = TopologyPlan.build(apartment_programme(), apartment_graph(), "Entrée")

    assert plan.gradient["Chambre 1"] is Zone.PRIVATE
    assert plan.zones["Cuisine"] == "day"
    assert plan.rooms_in(Zone.PRIVATE) == ["Chambre 1", "Chambre 2", "SDB"]

    restored = TopologyPlan.from_json(json.loads(json.dumps(plan.to_json())))
    assert restored.graph == plan.graph
    assert restored.gradient == plan.gradient
    assert restored.zones == plan.zones
    assert [r.nom for r in restored.programme.rooms] == [
        r.nom for r in plan.programme.rooms
    ]
    assert restored.programme.total_utile == pytest.approx(plan.programme.total_utile)


def test_a_plan_naming_rooms_the_programme_lacks_is_rejected():
    graph = ProgrammeGraph([Relation("Séjour", "Garage", R.CONNECTED)])
    with pytest.raises(ValueError, match="Garage"):
        TopologyPlan.build(apartment_programme(), graph, "Entrée")


def test_an_entry_outside_the_programme_is_rejected():
    with pytest.raises(ValueError, match="not in the programme"):
        TopologyPlan.build(apartment_programme(), apartment_graph(), "Perron")
