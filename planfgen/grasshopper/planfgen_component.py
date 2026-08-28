"""GhPython component — build a PLANFGEN plan in Rhino.

Replaces the v1 component, which took the *bounding box* of a Voronoi cell and
made a `PlaneSurface` from it. That rectangle was never the room; it was the
smallest box the room fitted inside, and every area it reported in Rhino was a
different number from the one the engine had computed. Here a space is a closed
polyline through the coordinates the engine exported, so what appears in Rhino
is what the engine measured — `document/gh.py` and `tests/test_gh.py` exist to
guarantee that.

Drop this into a GhPython component.

    Inputs   path        str   the JSON written by write_gh_json
             height      float storey height, metres          (default 2.80)
             net         bool  outline the net polygon too    (default True)
    Outputs  spaces      Brep  one capped surface per room
             walls       Brep  one extrusion per wall solid
             doors       Point one per door, at its centre
             windows     Point one per window, at its centre
             shafts      Brep  one extrusion per shaft
             report      str   what was read

This file is not imported by the engine and is not covered by the test suite:
it only runs inside Rhino, where `Rhino.Geometry` exists.
"""

import json

import Rhino.Geometry as rg  # noqa: F401  (provided by the Rhino runtime)

#: The schema this component understands. `to_gh_json` writes it.
EXPECTS = "2.0"


def _polyline(points, z=0.0):
    """A closed polyline curve through a list of [x, y] pairs."""
    pts = [rg.Point3d(float(x), float(y), z) for x, y in points]
    pts.append(pts[0])
    return rg.PolylineCurve(pts)


def _cap(curve):
    """The planar surface a closed curve bounds, as a Brep."""
    breps = rg.Brep.CreatePlanarBreps([curve], 1e-6)
    return breps[0] if breps else None


def _extrude(curve, height):
    """A solid from a closed planar curve."""
    extrusion = rg.Extrusion.Create(curve, -float(height), True)
    return extrusion.ToBrep() if extrusion else None


def _wall_rectangle(wall):
    """The wall solid's footprint: length by thickness, centred on the axis."""
    (x0, y0), (x1, y1) = wall["p0"], wall["p1"]
    half = wall["thickness"] / 2.0
    if abs(y1 - y0) < 1e-9:  # horizontal
        return [[x0, y0 - half], [x1, y0 - half], [x1, y0 + half], [x0, y0 + half]]
    return [[x0 - half, y0], [x0 - half, y1], [x0 + half, y1], [x0 + half, y0]]


def build(path, height=2.80, net=True):
    """Read the bridge document and return the Rhino geometry it describes."""
    with open(path, "r") as handle:
        plan = json.load(handle)

    version = plan.get("schema_version")
    if version != EXPECTS:
        return [], [], [], [], [], (
            "schema_version %r, this component expects %r" % (version, EXPECTS)
        )

    spaces, walls, doors, windows, shafts = [], [], [], [], []

    for space in plan["spaces"]:
        outline = space["net_outline"] if net else space["outline"]
        surface = _cap(_polyline(outline))
        if surface:
            spaces.append(surface)

    for wall in plan["walls"]:
        solid = _extrude(_polyline(_wall_rectangle(wall)), height)
        if solid:
            walls.append(solid)

    for door in plan["openings"]["doors"]:
        x, y = door["position"]
        doors.append(rg.Point3d(x, y, 0.0))

    for window in plan["openings"]["windows"]:
        x, y = window["position"]
        windows.append(rg.Point3d(x, y, (window["allege"] + window["head"]) / 2.0))

    for shaft in plan["shafts"]:
        x, y, w, h = shaft["x"], shaft["y"], shaft["w"], shaft["h"]
        footprint = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
        solid = _extrude(_polyline(footprint), height)
        if solid:
            shafts.append(solid)

    totals = plan.get("totals", {})
    report = "%d spaces, %.2f m2 utile, %d walls, %d doors, %d windows, %d shafts" % (
        len(spaces),
        totals.get("surface_utile", 0.0),
        len(walls),
        len(doors),
        len(windows),
        len(shafts),
    )
    return spaces, walls, doors, windows, shafts, report


# GhPython assigns the component inputs as module-level names and reads the
# outputs back off them, so the call sits at module scope.
if "path" in dir():
    spaces, walls, doors, windows, shafts, report = build(
        path,
        height if "height" in dir() and height else 2.80,
        net if "net" in dir() else True,
    )
