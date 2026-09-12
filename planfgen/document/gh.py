"""L8 — the Grasshopper bridge, carrying rectangles that are actually rectangles.

v1's component built a `PlaneSurface` from the *bounding box* of a Voronoi cell,
because a Voronoi cell has no width and height to export. The rectangle it drew
was therefore never the room; it was the smallest box the room happened to fit
inside. That is the failure this file exists to make impossible, and the round
trip in `test_gh.py` is what pins it: rebuild a rectangle from the exported
`x, y, w, h` and it must reproduce the space's own axis polygon exactly.

Faces are rectangles in every plan this engine produces, but the wall graph can
enclose a rectilinear face, so `outline` carries the true shape and
`rectangular` says whether the bounding box is the whole story.
"""

from __future__ import annotations

from pathlib import Path

from shapely.geometry import Polygon

from planfgen.fabric.plan import FabricPlan

#: Bumped whenever the shape of this document changes. The component checks it.
SCHEMA_VERSION = "2.0"

#: Coordinates are written at this precision; a tenth of a millimetre.
PLACES = 4


def _points(polygon: Polygon) -> list[list[float]]:
    return [
        [round(x, PLACES), round(y, PLACES)]
        for x, y in list(polygon.exterior.coords)[:-1]
    ]


def _is_rectangle(polygon: Polygon) -> bool:
    minx, miny, maxx, maxy = polygon.bounds
    return abs(polygon.area - (maxx - minx) * (maxy - miny)) <= 1e-9


def _space(nom: str, space) -> dict:
    minx, miny, maxx, maxy = space.axis_polygon.bounds
    net_w, net_h = space.net_dims()
    return {
        "nom": nom,
        "kind": space.kind.name,
        "x": round(minx, PLACES),
        "y": round(miny, PLACES),
        "w": round(maxx - minx, PLACES),
        "h": round(maxy - miny, PLACES),
        "rectangular": _is_rectangle(space.axis_polygon),
        "outline": _points(space.axis_polygon),
        "net_outline": _points(space.net_polygon),
        "net_w": round(net_w, PLACES),
        "net_h": round(net_h, PLACES),
        "surface_utile": round(space.surface_utile, PLACES),
        "axis_area": round(space.axis_polygon.area, PLACES),
    }


def to_gh_json(fabric: FabricPlan, openings=None, shafts=None) -> dict:
    """Everything Rhino needs to rebuild the plan, and nothing it does not.

    Openings refer to walls by index into `walls`, because a JSON document has
    no object identity and a door that names its wall by geometry would have to
    be matched back by comparing floats.
    """
    walls = list(fabric.graph.walls)
    index = {id(wall): i for i, wall in enumerate(walls)}
    profile = fabric.profile

    doors, windows = [], []
    if openings is not None:
        for door in openings.doors:
            low, high = door.span
            doors.append(
                {
                    "wall": index.get(id(door.wall), -1),
                    "t": round(door.t, 6),
                    "leaf": round(door.leaf, PLACES),
                    "swing_into": door.swing_into,
                    "swing_side": door.swing_side,
                    "hinge": door.hinge,
                    "span": [round(low, PLACES), round(high, PLACES)],
                    "position": [round(v, PLACES) for v in door.position()],
                }
            )
        for window in openings.windows:
            low, high = window.span
            windows.append(
                {
                    "wall": index.get(id(window.wall), -1),
                    "t": round(window.t, 6),
                    "width": round(window.width, PLACES),
                    "allege": round(window.allege, PLACES),
                    "head": round(window.head, PLACES),
                    "span": [round(low, PLACES), round(high, PLACES)],
                    "position": [round(v, PLACES) for v in window.position()],
                    "glazing": round(window.glazing, PLACES),
                }
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "units": "m",
        "parcel": {
            "outline": _points(fabric.parcel.outline),
            "north": fabric.parcel.north,
            "entry_edge": fabric.parcel.entry_edge,
            "edges": [
                {"index": edge.index, "kind": edge.kind.name, "openable": edge.kind.openable}
                for edge in fabric.parcel.edges
            ],
        },
        "spaces": [_space(nom, space) for nom, space in fabric.spaces.items()],
        "walls": [
            {
                "p0": [round(wall.p0[0], PLACES), round(wall.p0[1], PLACES)],
                "p1": [round(wall.p1[0], PLACES), round(wall.p1[1], PLACES)],
                "kind": wall.kind.name,
                "bearing": wall.kind.bearing,
                "thickness": round(profile.thickness_of(wall.kind.value), PLACES),
                "length": round(wall.length, PLACES),
                "stack_id": wall.stack_id,
            }
            for wall in walls
        ],
        "openings": {"doors": doors, "windows": windows},
        "shafts": [
            {
                "x": round(shaft.x, PLACES),
                "y": round(shaft.y, PLACES),
                "w": round(shaft.w, PLACES),
                "h": round(shaft.h, PLACES),
                "kind": shaft.kind.name,
                "stack_id": shaft.stack_id,
            }
            for shaft in (shafts or [])
        ],
        "totals": {
            "surface_utile": round(fabric.total_utile, PLACES),
            "spaces": len(fabric.spaces),
            "walls": len(walls),
        },
    }


def write_gh_json(fabric: FabricPlan, path: str | Path, openings=None, shafts=None) -> dict:
    """Write the bridge document and return it."""
    import json

    document = to_gh_json(fabric, openings, shafts)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
    return document


def rebuild_rectangle(space: dict) -> Polygon:
    """The rectangle a consumer would build from `x, y, w, h`.

    Here so the round trip is tested against the same construction Grasshopper
    performs, rather than against a second implementation of it.
    """
    x, y, w, h = space["x"], space["y"], space["w"], space["h"]
    return Polygon([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])
