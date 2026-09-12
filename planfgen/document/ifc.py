"""L8 — IFC, so the plan can go into somebody else's model.

Optional. `ifcopenshell` is not a dependency of the engine: `available()` says
whether it is installed and `export_ifc` raises a plain `RuntimeError` if it is
not, so nothing else in the project has to care.

An `IfcSpace` carries the *net* area, because that is the number the programme
was written in and the number a schedule will be checked against. Exporting the
axis area would hand the next consultant a room several percent larger than the
one that gets built — the same lie v1's Grasshopper component told in Rhino.
"""

from __future__ import annotations

from pathlib import Path

from planfgen.fabric.plan import FabricPlan
from planfgen.fabric.solidify import wall_solids

#: Default storey height, in metres. A placeholder, like every other dimension
#: in this project that is not in `brief/regulation.py`.
STOREY_HEIGHT = 2.80


def available() -> bool:
    """True if ifcopenshell can be imported."""
    try:
        import ifcopenshell  # noqa: F401
    except Exception:
        return False
    return True


def _profile(model, points):
    """A closed arbitrary profile from a list of (x, y)."""
    polyline = model.create_entity(
        "IfcPolyline",
        Points=[model.create_entity("IfcCartesianPoint", Coordinates=(float(x), float(y)))
                for x, y in points],
    )
    polyline.Points = list(polyline.Points) + [polyline.Points[0]]
    return model.create_entity(
        "IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=polyline
    )


def _extrude(model, points, height, placement):
    """A solid swept up from a footprint."""
    return model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=_profile(model, points),
        Position=placement,
        ExtrudedDirection=model.create_entity(
            "IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)
        ),
        Depth=float(height),
    )


def export_ifc(
    fabric: FabricPlan, path: str | Path, height: float = STOREY_HEIGHT
) -> None:
    """Write the plan as IFC4: a space per room, a wall per solid, and openings.

    Raises `RuntimeError` if ifcopenshell is not installed — this export is
    optional and the engine does not depend on it.
    """
    if not available():
        raise RuntimeError(
            "ifcopenshell is not installed; IFC export is optional. "
            "pip install ifcopenshell"
        )

    import ifcopenshell
    import ifcopenshell.api

    run = ifcopenshell.api.run
    model = ifcopenshell.file(schema="IFC4")

    project = run("root.create_entity", model, ifc_class="IfcProject", name="PLANFGEN")
    run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})
    context = run("context.add_context", model, context_type="Model")
    body = run(
        "context.add_context",
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=context,
    )

    site = run("root.create_entity", model, ifc_class="IfcSite", name="Parcelle")
    building = run("root.create_entity", model, ifc_class="IfcBuilding", name="Batiment")
    storey = run(
        "root.create_entity", model, ifc_class="IfcBuildingStorey", name="Niveau 0"
    )
    run("aggregate.assign_object", model, products=[site], relating_object=project)
    run("aggregate.assign_object", model, products=[building], relating_object=site)
    run("aggregate.assign_object", model, products=[storey], relating_object=building)

    placement = model.create_entity(
        "IfcAxis2Placement3D",
        Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
    )

    def _shape(points, depth):
        solid = _extrude(model, points, depth, placement)
        return model.create_entity(
            "IfcProductDefinitionShape",
            Representations=[
                model.create_entity(
                    "IfcShapeRepresentation",
                    ContextOfItems=body,
                    RepresentationIdentifier="Body",
                    RepresentationType="SweptSolid",
                    Items=[solid],
                )
            ],
        )

    def _ring(polygon):
        return list(polygon.exterior.coords)[:-1]

    spaces = []
    for nom, space in fabric.spaces.items():
        product = run("root.create_entity", model, ifc_class="IfcSpace", name=nom)
        product.LongName = nom
        product.Representation = _shape(_ring(space.net_polygon), height)
        run(
            "pset.edit_pset",
            model,
            pset=run("pset.add_pset", model, product=product, name="Pset_SpaceCommon"),
            properties={"GrossPlannedArea": float(space.axis_polygon.area),
                        "NetPlannedArea": float(space.surface_utile)},
        )
        spaces.append(product)
    if spaces:
        run("aggregate.assign_object", model, products=spaces, relating_object=storey)

    walls = []
    for wall, solid in wall_solids(fabric.graph, fabric.profile):
        product = run(
            "root.create_entity", model, ifc_class="IfcWall", name=wall.kind.name
        )
        product.Representation = _shape(_ring(solid), height)
        walls.append(product)
    if walls:
        run("spatial.assign_container", model, products=walls, relating_structure=storey)

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(target))


def export_ifc_openings(model_path: str | Path, openings) -> None:
    """Placeholder for door and window products.

    Deliberately not implemented. An `IfcDoor` is only meaningful with an
    `IfcOpeningElement` voiding the wall it sits in, and a door written without
    one is a symbol floating beside a solid wall — which is exactly the kind of
    drawing this project exists to stop producing. `document/dxf.py` already
    cuts the openings properly; doing the same in IFC is a session of its own.
    """
    raise NotImplementedError(
        "IfcDoor needs an IfcOpeningElement voiding its wall; see the docstring"
    )
