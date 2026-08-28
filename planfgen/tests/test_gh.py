"""The Grasshopper bridge — and the round trip v1 could never have passed.

v1's component built a `PlaneSurface` from the bounding box of a Voronoi cell.
A Voronoi cell has no width and height, so the rectangle it drew in Rhino was
the smallest box the room fitted inside, never the room, and the area Rhino
reported was a different number from the one the engine had computed.

Here, rebuilding a rectangle from the exported `x, y, w, h` has to reproduce the
space's own axis polygon exactly. That is only possible because a space is a
face of the wall graph and every face this engine makes is a rectangle.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from planfgen.document import (
    SCHEMA_VERSION,
    rebuild_rectangle,
    to_gh_json,
    write_gh_json,
)
from planfgen.openings import place_openings
from planfgen.services import assign_stack_ids, place_shafts
from planfgen.services.stacking import Level
from planfgen.partition import StructuralGrid

from planfgen.tests.test_openings import FLAT_RELATIONS, topology_for
from planfgen.tests.test_services import P, flat


def furnished():
    """The reference flat with its openings, shafts and stack ids."""
    fabric = flat()
    report = place_openings(fabric, topology_for(FLAT_RELATIONS), P)
    shafts = place_shafts(fabric, P)
    level = Level(0, 2.80, fabric, shafts)
    assign_stack_ids(level, StructuralGrid.from_span(12.0, 9.0))
    return fabric, report, shafts


# --- THE ROUND TRIP ---------------------------------------------------------


def test_every_exported_rectangle_is_the_room_it_came_from():
    """THE test. x, y, w, h must describe the space, not merely contain it."""
    fabric = flat()
    document = to_gh_json(fabric)

    assert len(document["spaces"]) == len(fabric.spaces)
    for exported in document["spaces"]:
        space = fabric.spaces[exported["nom"]]
        rebuilt = rebuild_rectangle(exported)

        assert rebuilt.area == pytest.approx(space.axis_polygon.area, abs=1e-9)
        assert rebuilt.symmetric_difference(space.axis_polygon).area == pytest.approx(
            0.0, abs=1e-9
        )
        assert exported["rectangular"] is True


def test_the_exported_area_is_the_area_the_engine_measured():
    """v1 reported one number and drew another."""
    fabric = flat()
    for exported in to_gh_json(fabric)["spaces"]:
        space = fabric.spaces[exported["nom"]]
        assert exported["surface_utile"] == pytest.approx(space.surface_utile, abs=1e-4)
        assert exported["axis_area"] == pytest.approx(space.axis_polygon.area, abs=1e-4)
        assert exported["surface_utile"] < exported["axis_area"], "walls cost something"


def test_the_net_outline_sits_inside_the_axis_outline():
    fabric = flat()
    for exported in to_gh_json(fabric)["spaces"]:
        assert len(exported["outline"]) >= 4
        assert len(exported["net_outline"]) == 4
        assert exported["net_w"] < exported["w"] and exported["net_h"] < exported["h"]


def test_an_axis_outline_may_carry_the_nodes_of_its_neighbours():
    """The corridor is a rectangle with seven vertices.

    Its long sides are cut where the rooms either side meet them, and
    polygonize keeps a vertex at every node. Still a rectangle — which is why
    the round trip holds — but a consumer walking `outline` must not assume
    four points. The net polygon drops the redundant ones.
    """
    fabric = flat()
    corridor = next(
        s for s in to_gh_json(fabric)["spaces"] if s["nom"] == "Couloir"
    )
    assert len(corridor["outline"]) == 7
    assert len(corridor["net_outline"]) == 4
    assert corridor["rectangular"] is True
    assert rebuild_rectangle(corridor).symmetric_difference(
        fabric.spaces["Couloir"].axis_polygon
    ).area == pytest.approx(0.0, abs=1e-9)


# --- the document -----------------------------------------------------------


def test_the_document_declares_its_schema_and_units():
    document = to_gh_json(flat())
    assert document["schema_version"] == SCHEMA_VERSION == "2.0"
    assert document["units"] == "m"
    assert document["totals"]["spaces"] == len(document["spaces"])
    assert document["totals"]["walls"] == len(document["walls"])


def test_walls_carry_their_kind_thickness_and_stack_id():
    fabric, _report, _shafts = furnished()
    document = to_gh_json(fabric)

    for exported, wall in zip(document["walls"], fabric.graph.walls):
        assert exported["kind"] == wall.kind.name
        assert exported["bearing"] == wall.kind.bearing
        assert exported["thickness"] == pytest.approx(
            P.thickness_of(wall.kind.value), abs=1e-9
        )
        assert exported["length"] == pytest.approx(wall.length, abs=1e-4)
        assert exported["stack_id"] == wall.stack_id


def test_openings_point_at_walls_by_index():
    """A JSON document has no object identity, so a door names its wall by place."""
    fabric, report, shafts = furnished()
    document = to_gh_json(fabric, report, shafts)

    assert len(document["openings"]["doors"]) == len(report.doors)
    assert len(document["openings"]["windows"]) == len(report.windows)

    for exported, door in zip(document["openings"]["doors"], report.doors):
        assert 0 <= exported["wall"] < len(document["walls"])
        assert fabric.graph.walls[exported["wall"]] is door.wall
        assert exported["position"] == pytest.approx(door.position(), abs=1e-4)
        assert exported["swing_side"] in (-1, 1)

    for exported, window in zip(document["openings"]["windows"], report.windows):
        assert fabric.graph.walls[exported["wall"]] is window.wall
        assert exported["glazing"] == pytest.approx(window.glazing, abs=1e-4)


def test_shafts_and_the_parcel_come_across():
    fabric, report, shafts = furnished()
    document = to_gh_json(fabric, report, shafts)

    assert len(document["shafts"]) == len(shafts)
    assert all(s["stack_id"].startswith("SH:") for s in document["shafts"])

    parcel = document["parcel"]
    assert len(parcel["outline"]) == 4
    assert parcel["entry_edge"] == 0
    assert [e["openable"] for e in parcel["edges"]] == [True, False, True, False]


def test_a_plan_with_no_openings_still_exports():
    document = to_gh_json(flat())
    assert document["openings"] == {"doors": [], "windows": []}
    assert document["shafts"] == []


# --- the file ---------------------------------------------------------------


def test_write_gh_json_round_trips_through_disk(tmp_path: Path):
    fabric, report, shafts = furnished()
    target = tmp_path / "plan.json"
    written = write_gh_json(fabric, target, report, shafts)

    reloaded = json.loads(target.read_text(encoding="utf-8"))
    assert reloaded == written

    for exported in reloaded["spaces"]:
        space = fabric.spaces[exported["nom"]]
        assert rebuild_rectangle(exported).symmetric_difference(
            space.axis_polygon
        ).area == pytest.approx(0.0, abs=1e-9)


def test_the_component_script_reads_the_schema_this_writer_produces():
    """The component refuses a document it does not understand, so the two
    constants have to agree. Read as text: the script imports Rhino."""
    source = (
        Path(__file__).parent.parent / "grasshopper" / "planfgen_component.py"
    ).read_text(encoding="utf-8")
    assert f'EXPECTS = "{SCHEMA_VERSION}"' in source
    assert "net_outline" in source, "it builds the net polygon, not a bounding box"
