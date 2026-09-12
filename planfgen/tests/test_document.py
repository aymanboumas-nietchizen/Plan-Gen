"""L8 tests — the DXF, and whether it reopens as a drawing.

A file that ezdxf will write but not read back is worse than no file, so every
test here goes through `readfile` rather than inspecting the document in memory.
What is checked is what a consultant would find on opening it: the layers, one
solid per wall, and a stamp in every room carrying the area the engine computed.
"""

from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from planfgen.document import (
    LAYERS,
    WALL_LAYER,
    DimensionChain,
    export_dxf,
    exterior_chains,
    interior_chains,
    room_stamp,
    stamp_text,
)
from planfgen.fabric import WallKind
from planfgen.openings import place_openings
from planfgen.services import place_shafts
from planfgen.topology import ProgrammeGraph, Relation, RelationType as R

from planfgen.tests.test_openings import FLAT_RELATIONS, topology_for
from planfgen.tests.test_services import P, flat


def plan_with_openings():
    fabric = flat()
    report = place_openings(fabric, topology_for(FLAT_RELATIONS), P)
    return fabric, report, place_shafts(fabric, P)


def structural_flat():
    """The same plan with its two spine walls retyped as bearing.

    A plan cut entirely with cloisons has nothing structural to dimension, so
    the interior-chain test needs a plan that has.
    """
    fabric = flat()
    for wall in fabric.graph.walls:
        if wall.is_vertical and abs(wall.p0[0] - 5.0) < 1e-9:
            wall.kind = WallKind.PORTEUR
        if wall.is_horizontal and abs(wall.p0[1] - 5.0) < 1e-9:
            wall.kind = WallKind.PORTEUR
    return fabric


def written(tmp_path: Path, name: str = "plan.dxf", **kwargs):
    fabric = kwargs.pop("fabric", None) or flat()
    target = tmp_path / name
    export_dxf(fabric, target, **kwargs)
    return fabric, target, ezdxf.readfile(target)


# --- dimensions -------------------------------------------------------------


def test_one_exterior_chain_per_side_reading_the_bays_that_side_has():
    """Top and bottom are not the same run, and a drawing must show both."""
    chains = exterior_chains(flat())
    assert len(chains) == 4
    assert [c.axis for c in chains] == ["x", "x", "y", "y"]

    bottom = chains[0]
    assert bottom.ticks == pytest.approx([0.0, 5.0, 6.3, 9.15, 12.0])
    assert bottom.spans == pytest.approx([5.0, 1.3, 2.85, 2.85])
    assert bottom.total == pytest.approx(12.0)

    top = chains[1]
    assert 9.15 not in top.ticks, "the SDB/WC wall does not reach the back"
    assert top.total == pytest.approx(12.0)


def test_a_chain_of_one_tick_measures_nothing():
    assert DimensionChain("x", 0.0, [3.0]).spans == []
    assert DimensionChain("x", 0.0, [3.0]).total == 0.0


def test_a_plan_of_cloisons_has_no_interior_chains():
    """Correct rather than empty: there is nothing structural in it."""
    fabric = flat()
    assert not any(w.kind is WallKind.PORTEUR for w in fabric.graph.walls)
    assert interior_chains(fabric) == []


def test_interior_chains_follow_the_bearing_lines():
    chains = interior_chains(structural_flat())
    assert len(chains) == 2

    vertical = next(c for c in chains if c.axis == "y")
    assert vertical.position == pytest.approx(5.0)
    assert vertical.ticks == pytest.approx([0.0, 9.0])

    horizontal = next(c for c in chains if c.axis == "x")
    assert horizontal.position == pytest.approx(5.0)
    assert horizontal.ticks == pytest.approx([0.0, 12.0])


def test_a_room_stamp_carries_what_the_engine_measured():
    fabric = flat()
    stamp = room_stamp(fabric.spaces["Sejour"])

    assert stamp["nom"] == "Sejour"
    assert stamp["surface_utile"] == pytest.approx(23.04, abs=1e-9)
    assert (stamp["net_w"], stamp["net_h"]) == pytest.approx((4.80, 4.80))
    assert "23.04 m2" in stamp_text(stamp)


# --- the file ---------------------------------------------------------------


def test_export_writes_a_file_ezdxf_reopens(tmp_path: Path):
    _fabric, target, doc = written(tmp_path)
    assert target.exists() and target.stat().st_size > 0
    assert doc.modelspace() is not None


def test_every_expected_layer_exists(tmp_path: Path):
    _fabric, _target, doc = written(tmp_path)
    for semantic, (layer, colour, lineweight) in LAYERS.items():
        assert layer in doc.layers, semantic
        assert doc.layers.get(layer).color == colour
        assert doc.layers.get(layer).dxf.lineweight == lineweight


def test_one_closed_polyline_per_wall_solid(tmp_path: Path):
    """With nothing cut into them, a wall is one solid."""
    fabric, _target, doc = written(tmp_path)
    wall_layers = {LAYERS[WALL_LAYER[k]][0] for k in WallKind}

    polylines = [
        e
        for e in doc.modelspace()
        if e.dxftype() == "LWPOLYLINE" and e.dxf.layer in wall_layers
    ]
    assert len(polylines) == len(fabric.graph.walls)
    for polyline in polylines:
        assert polyline.closed
        assert len(polyline) == 4, "a wall solid is a rectangle"


def test_each_wall_is_drawn_on_the_layer_for_its_kind(tmp_path: Path):
    fabric, _target, doc = written(tmp_path)
    expected: dict[str, int] = {}
    for wall in fabric.graph.walls:
        layer = LAYERS[WALL_LAYER[wall.kind]][0]
        expected[layer] = expected.get(layer, 0) + 1

    got: dict[str, int] = {}
    for entity in doc.modelspace():
        if entity.dxftype() == "LWPOLYLINE" and entity.dxf.layer in expected:
            got[entity.dxf.layer] = got.get(entity.dxf.layer, 0) + 1
    assert got == expected


def test_a_stamp_exists_for_every_space_and_carries_its_net_area(tmp_path: Path):
    fabric, _target, doc = written(tmp_path)
    stamps = [e for e in doc.modelspace() if e.dxftype() == "MTEXT"]

    assert len(stamps) == len(fabric.spaces)
    by_nom = {}
    for stamp in stamps:
        assert stamp.dxf.layer == LAYERS["TEXTE_PIECE"][0]
        by_nom[stamp.text.split("\\P")[0]] = stamp.text

    assert set(by_nom) == set(fabric.spaces)
    for nom, space in fabric.spaces.items():
        assert f"{space.surface_utile:.2f} m2" in by_nom[nom], nom


def test_dimension_chains_are_real_dimension_entities(tmp_path: Path):
    fabric, _target, doc = written(tmp_path)
    dims = [e for e in doc.modelspace() if e.dxftype() == "DIMENSION"]

    expected = sum(len(c.spans) for c in exterior_chains(fabric) + interior_chains(fabric))
    assert len(dims) == expected > 0
    assert all(d.dxf.layer == LAYERS["COTATION"][0] for d in dims)


def test_every_wall_gets_a_centreline_on_the_axe_layer(tmp_path: Path):
    fabric, _target, doc = written(tmp_path)
    axes = [
        e
        for e in doc.modelspace()
        if e.dxftype() == "LINE" and e.dxf.layer == LAYERS["AXE"][0]
    ]
    assert len(axes) == len(fabric.graph.walls)


# --- openings and shafts ----------------------------------------------------


def test_openings_are_gaps_in_the_wall_not_symbols_over_it(tmp_path: Path):
    """What is drawn is what would be built."""
    fabric, report, shafts = plan_with_openings()
    plain = tmp_path / "plain.dxf"
    cut = tmp_path / "cut.dxf"
    export_dxf(fabric, plain)
    export_dxf(fabric, cut, openings=report, shafts=shafts)

    def wall_polys(path):
        wall_layers = {LAYERS[WALL_LAYER[k]][0] for k in WallKind}
        return [
            e
            for e in ezdxf.readfile(path).modelspace()
            if e.dxftype() == "LWPOLYLINE" and e.dxf.layer in wall_layers
        ]

    assert report.doors and report.windows
    assert len(wall_polys(cut)) > len(wall_polys(plain)), "each opening splits a wall"


def test_a_door_gets_a_leaf_and_a_swing_arc(tmp_path: Path):
    fabric, report, shafts = plan_with_openings()
    target = tmp_path / "plan.dxf"
    export_dxf(fabric, target, openings=report, shafts=shafts)
    doc = ezdxf.readfile(target)

    arcs = [e for e in doc.modelspace() if e.dxftype() == "ARC"]
    assert len(arcs) == len(report.doors)

    leaves = sorted(round(d.leaf, 6) for d in report.doors)
    assert sorted(round(a.dxf.radius, 6) for a in arcs) == leaves
    assert all(a.dxf.layer == LAYERS["OUVERTURE_PORTE"][0] for a in arcs)
    assert all(abs(a.dxf.end_angle - a.dxf.start_angle) == pytest.approx(90.0)
               for a in arcs), "a leaf turns through a right angle"

    leaf_lines = [
        e for e in doc.modelspace()
        if e.dxftype() == "LINE" and e.dxf.layer == LAYERS["OUVERTURE_PORTE"][0]
    ]
    assert len(leaf_lines) == len(report.doors)


def test_a_shaft_is_drawn_on_the_gaine_layer(tmp_path: Path):
    fabric, report, shafts = plan_with_openings()
    target = tmp_path / "plan.dxf"
    export_dxf(fabric, target, openings=report, shafts=shafts)
    doc = ezdxf.readfile(target)

    gaines = [
        e
        for e in doc.modelspace()
        if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == LAYERS["GAINE"][0]
    ]
    assert len(gaines) == len(shafts) == 2


def test_the_drawing_is_in_metres(tmp_path: Path):
    _fabric, _target, doc = written(tmp_path)
    assert doc.header["$INSUNITS"] == 6


# --- IFC, optional ----------------------------------------------------------

from planfgen.document.ifc import available, export_ifc  # noqa: E402

ifc_only = pytest.mark.skipif(not available(), reason="ifcopenshell not installed")


def test_export_ifc_says_so_when_it_cannot():
    """The engine does not depend on ifcopenshell, so absence is not a crash."""
    if available():
        pytest.skip("ifcopenshell is installed here")
    with pytest.raises(RuntimeError, match="optional"):
        export_ifc(flat(), "unused.ifc")


@ifc_only
def test_ifc_carries_a_space_per_room_and_a_wall_per_solid(tmp_path: Path):
    import ifcopenshell

    fabric = flat()
    target = tmp_path / "plan.ifc"
    export_ifc(fabric, target)

    model = ifcopenshell.open(str(target))
    assert model.schema == "IFC4"
    assert len(model.by_type("IfcSpace")) == len(fabric.spaces)
    assert len(model.by_type("IfcWall")) == len(fabric.graph.walls)
    for cls in ("IfcProject", "IfcSite", "IfcBuilding", "IfcBuildingStorey"):
        assert len(model.by_type(cls)) == 1, cls


@ifc_only
def test_an_ifc_space_carries_the_net_area_not_the_axis_area(tmp_path: Path):
    """The number the programme was written in, and a schedule checks against."""
    import ifcopenshell
    import ifcopenshell.util.element as element

    fabric = flat()
    target = tmp_path / "plan.ifc"
    export_ifc(fabric, target)

    model = ifcopenshell.open(str(target))
    by_nom = {s.Name: s for s in model.by_type("IfcSpace")}
    assert set(by_nom) == set(fabric.spaces)

    for nom, space in fabric.spaces.items():
        pset = element.get_psets(by_nom[nom])["Pset_SpaceCommon"]
        assert pset["NetPlannedArea"] == pytest.approx(space.surface_utile, abs=1e-6)
        assert pset["GrossPlannedArea"] == pytest.approx(
            space.axis_polygon.area, abs=1e-6
        )
        assert pset["NetPlannedArea"] < pset["GrossPlannedArea"]


@ifc_only
def test_ifc_doors_are_deliberately_not_written(tmp_path: Path):
    """A door without an IfcOpeningElement is a symbol beside a solid wall."""
    from planfgen.document.ifc import export_ifc_openings

    with pytest.raises(NotImplementedError, match="IfcOpeningElement"):
        export_ifc_openings(tmp_path / "plan.ifc", None)

