"""L8 — DXF, the format the drawing has to leave in.

Walls go out as solids on a layer per type, not as lines, because the whole
claim of v2 is that a wall has a thickness — a DXF of hairlines would throw away
the thing the engine exists to compute. Openings are gaps cut in those solids
rather than symbols laid over them, so what is drawn is what would be built.

Layer names are French, like the rest of the domain vocabulary, and one layer
per wall kind so a consultant can turn the partitions off and see the structure.
"""

from __future__ import annotations

import math
from pathlib import Path

import ezdxf

from planfgen.document.dimensions import (
    exterior_chains,
    interior_chains,
    room_stamp,
    stamp_text,
)
from planfgen.fabric.axis import WallAxis, WallKind
from planfgen.fabric.plan import FabricPlan
from planfgen.fabric.solidify import wall_solids

#: Semantic name -> (layer, ACI colour, lineweight in 1/100 mm).
LAYERS: dict[str, tuple[str, int, int]] = {
    "MUR_PORTEUR": ("MUR_PORTEUR", 1, 50),
    "CLOISON": ("CLOISON", 8, 18),
    "MUR_FACADE": ("MUR_FACADE", 7, 50),
    "MUR_WET": ("MUR_WET", 4, 35),
    "OUVERTURE_PORTE": ("OUVERTURE_PORTE", 3, 13),
    "OUVERTURE_FENETRE": ("OUVERTURE_FENETRE", 5, 13),
    "COTATION": ("COTATION", 2, 9),
    "TEXTE_PIECE": ("TEXTE_PIECE", 7, 9),
    "GAINE": ("GAINE", 6, 25),
    "AXE": ("AXE", 8, 5),
}

#: Which layer a wall of each kind is drawn on.
WALL_LAYER: dict[WallKind, str] = {
    WallKind.FACADE: "MUR_FACADE",
    WallKind.PORTEUR: "MUR_PORTEUR",
    WallKind.CLOISON: "CLOISON",
    WallKind.WET: "MUR_WET",
}

#: Height of the room-stamp text, in metres.
STAMP_HEIGHT = 0.22

#: Points on a door's swing arc.
ARC_SEGMENTS = 16


def _setup(doc) -> None:
    for layer, colour, lineweight in LAYERS.values():
        doc.layers.add(name=layer, color=colour, lineweight=lineweight)


def _openings_on(wall: WallAxis, openings) -> list[tuple[float, float]]:
    """The intervals along `wall`, in metres from p0, that are holes."""
    gaps = [
        opening.span
        for opening in openings
        if opening.wall is wall
    ]
    return sorted(gaps)


def _solid_runs(length: float, gaps: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """What is left of a wall once its openings are taken out."""
    runs: list[tuple[float, float]] = []
    cursor = 0.0
    for low, high in gaps:
        low, high = max(0.0, low), min(length, high)
        if low > cursor:
            runs.append((cursor, low))
        cursor = max(cursor, high)
    if cursor < length:
        runs.append((cursor, length))
    return [(a, b) for a, b in runs if b - a > 1e-9]


def _run_polygon(wall: WallAxis, low: float, high: float, half: float):
    """The four corners of one solid run of a wall."""
    (x0, y0) = wall.p0
    if wall.is_horizontal:
        return [
            (x0 + low, y0 - half),
            (x0 + high, y0 - half),
            (x0 + high, y0 + half),
            (x0 + low, y0 + half),
        ]
    return [
        (x0 - half, y0 + low),
        (x0 - half, y0 + high),
        (x0 + half, y0 + high),
        (x0 + half, y0 + low),
    ]


def _draw_solid(msp, points, layer: str, colour: int) -> None:
    msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})
    hatch = msp.add_hatch(color=colour, dxfattribs={"layer": layer})
    hatch.paths.add_polyline_path(points, is_closed=True)


def _draw_walls(msp, fabric: FabricPlan, openings) -> None:
    for wall, solid in wall_solids(fabric.graph, fabric.profile):
        layer, colour, _ = LAYERS[WALL_LAYER[wall.kind]]
        half = fabric.profile.thickness_of(wall.kind.value) / 2
        gaps = _openings_on(wall, openings)
        for low, high in _solid_runs(wall.length, gaps):
            _draw_solid(msp, _run_polygon(wall, low, high, half), layer, colour)
        msp.add_line(wall.p0, wall.p1, dxfattribs={"layer": LAYERS["AXE"][0]})


def _draw_doors(msp, doors) -> None:
    layer = LAYERS["OUVERTURE_PORTE"][0]
    for door in doors:
        low, _high = door.span
        wall = door.wall
        (x0, y0) = wall.p0
        if wall.is_horizontal:
            hinge = (x0 + low, y0)
            leaf_end = (hinge[0], y0 + door.leaf * (1 if door.swing_side >= 0 else -1))
            start = 90.0 if door.swing_side >= 0 else 270.0
            sweep = -90.0 if door.swing_side >= 0 else 90.0
        else:
            hinge = (x0, y0 + low)
            leaf_end = (x0 + door.leaf * (1 if door.swing_side >= 0 else -1), hinge[1])
            start = 0.0 if door.swing_side >= 0 else 180.0
            sweep = 90.0 if door.swing_side >= 0 else -90.0

        msp.add_line(hinge, leaf_end, dxfattribs={"layer": layer})
        end = start + sweep
        msp.add_arc(
            center=hinge,
            radius=door.leaf,
            start_angle=min(start, end),
            end_angle=max(start, end),
            dxfattribs={"layer": layer},
        )


def _draw_windows(msp, windows) -> None:
    layer = LAYERS["OUVERTURE_FENETRE"][0]
    for window in windows:
        low, high = window.span
        (x0, y0) = window.wall.p0
        if window.wall.is_horizontal:
            msp.add_line((x0 + low, y0), (x0 + high, y0), dxfattribs={"layer": layer})
        else:
            msp.add_line((x0, y0 + low), (x0, y0 + high), dxfattribs={"layer": layer})


def _draw_shafts(msp, shafts) -> None:
    layer, colour, _ = LAYERS["GAINE"]
    for shaft in shafts:
        points = [
            (shaft.x, shaft.y),
            (shaft.x + shaft.w, shaft.y),
            (shaft.x + shaft.w, shaft.y + shaft.h),
            (shaft.x, shaft.y + shaft.h),
        ]
        _draw_solid(msp, points, layer, colour)


def _draw_stamps(msp, fabric: FabricPlan) -> None:
    layer = LAYERS["TEXTE_PIECE"][0]
    for space in fabric.spaces.values():
        stamp = room_stamp(space)
        text = msp.add_mtext(
            stamp_text(stamp),
            dxfattribs={"layer": layer, "char_height": STAMP_HEIGHT},
        )
        text.set_location(stamp["centroid"], attachment_point=5)


def _draw_chains(msp, chains) -> None:
    layer = LAYERS["COTATION"][0]
    for chain in chains:
        for low, high in zip(chain.ticks, chain.ticks[1:]):
            if chain.axis == "x":
                p1, p2 = (low, chain.position), (high, chain.position)
                angle = 0.0
            else:
                p1, p2 = (chain.position, low), (chain.position, high)
                angle = 90.0
            dim = msp.add_linear_dim(
                base=p1,
                p1=p1,
                p2=p2,
                angle=angle,
                dimstyle="EZDXF",
                dxfattribs={"layer": layer},
            )
            dim.render()


def export_dxf(
    fabric: FabricPlan,
    path: str | Path,
    openings=None,
    shafts=None,
) -> None:
    """Write the plan as DXF. Always `saveas`, never `save`."""
    doors = list(openings.doors) if openings else []
    windows = list(openings.windows) if openings else []
    every_opening = doors + windows

    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6  # metres
    _setup(doc)
    msp = doc.modelspace()

    _draw_walls(msp, fabric, every_opening)
    _draw_doors(msp, doors)
    _draw_windows(msp, windows)
    _draw_shafts(msp, shafts or [])
    _draw_stamps(msp, fabric)
    _draw_chains(msp, exterior_chains(fabric) + interior_chains(fabric))

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(target)
