"""
export/dxf.py  -  Sprint 6 update
====================================
DXF export with optional wall, door and entrance layers.

Layers:
  ENVELOPE          - outline of the floor plan boundary (any polygon)
  ROOMS             - room polygons (centre-line, filled)
  WALLS_EXTERIOR    - exterior wall outline (thick, lineweight 50)
  WALLS_INTERIOR    - interior walls between rooms (lineweight 25)
  DOORS             - interior door openings (short line + arc swing)
  ENTRANCE          - entrance door (distinct colour)
"""

from __future__ import annotations

import os
from typing import Dict, Optional

from planfgen.core.geometry import Room, Envelope


def export_dxf(
    placed: Dict[str, Room],
    filename: str,
    envelope_or_W,
    H: float = None,
    output_dir: str = "./outputs",
    wall_system=None,
) -> str:
    """
    Export a layout to DXF R2010.

    Parameters
    ----------
    placed        : {nom: Room} layout dict
    filename      : output filename (no extension)
    envelope_or_W : Envelope object OR width W (float, backward compat)
    H             : envelope height (only for backward compat W/H pair)
    output_dir    : directory for output file
    wall_system   : optional WallSystem from build_wall_system()

    Returns
    -------
    Absolute path to the created .dxf file.
    """
    try:
        import ezdxf
    except ImportError:
        raise ImportError("pip install ezdxf>=1.1.0  for DXF export")

    # Resolve envelope
    if isinstance(envelope_or_W, Envelope):
        envelope = envelope_or_W
    elif isinstance(envelope_or_W, (int, float)) and H is not None:
        from planfgen.core.geometry import Envelope as Env
        envelope = Env.from_rect(float(envelope_or_W), float(H))
    else:
        raise TypeError("Pass Envelope or (W: float, H=float)")

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{filename}.dxf")

    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()

    # ── Envelope boundary (any polygon) ─────────────────────────────────────
    if "ENVELOPE" not in doc.layers:
        doc.layers.add("ENVELOPE", color=7)
    env_pts = list(envelope.polygon.exterior.coords)
    msp.add_lwpolyline(env_pts, close=True,
                       dxfattribs={"layer": "ENVELOPE", "linetype": "DASHED"})

    # ── Room polygons ────────────────────────────────────────────────────────
    for nom, room in placed.items():
        layer_name = _safe_layer_name(nom)
        aci = _rgb_to_aci(_hex_to_rgb(room.color))
        if layer_name not in doc.layers:
            doc.layers.add(layer_name, color=aci)

        # Use Shapely coords -> supports any polygon shape
        pts = [(c[0], c[1]) for c in room.coords]
        msp.add_lwpolyline(pts, close=True,
                           dxfattribs={"layer": layer_name, "lineweight": 25})

        label = f"{nom}  {room.area:.1f} m\u00b2"
        text_h = max(0.20, min(room.h * 0.12, 0.40))
        msp.add_text(label, dxfattribs={
            "layer": layer_name, "height": text_h,
            "insert": (room.cx, room.cy), "halign": 4,
        })

    # ── Walls (if wall_system provided) ──────────────────────────────────────
    if wall_system is not None:
        # Exterior walls
        if "WALLS_EXTERIOR" not in doc.layers:
            doc.layers.add("WALLS_EXTERIOR", color=7)
        # Interior walls
        if "WALLS_INTERIOR" not in doc.layers:
            doc.layers.add("WALLS_INTERIOR", color=8)
        # Doors
        if "DOORS" not in doc.layers:
            doc.layers.add("DOORS", color=4)   # cyan
        # Entrance
        if "ENTRANCE" not in doc.layers:
            doc.layers.add("ENTRANCE", color=2)  # yellow

        for wall in wall_system.walls:
            layer = "WALLS_EXTERIOR" if wall.wall_type == "exterior" else "WALLS_INTERIOR"
            lw    = 50 if wall.wall_type == "exterior" else 25
            msp.add_line(
                (wall.x0, wall.y0), (wall.x1, wall.y1),
                dxfattribs={"layer": layer, "lineweight": lw},
            )

        for door in wall_system.doors:
            layer = "ENTRANCE" if door.door_type == "entrance" else "DOORS"
            # Short perpendicular tick at door midpoint
            msp.add_circle(
                center=(door.cx, door.cy),
                radius=door.width / 2,
                dxfattribs={"layer": layer},
            )

    doc.saveas(out_path)
    return os.path.abspath(out_path)


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def _safe_layer_name(nom: str) -> str:
    for ch in r'/\<>|:;?*=`':
        nom = nom.replace(ch, "_")
    return nom[:255]


def _hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return (128, 128, 128)
    try:
        return (int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))
    except ValueError:
        return (128, 128, 128)


def _rgb_to_aci(rgb: tuple) -> int:
    r, g, b = rgb
    if max(r, g, b) < 64:   return 8
    if r > 200 and g < 100 and b < 100: return 1
    if r < 100 and g > 200 and b < 100: return 3
    if r < 100 and g < 100 and b > 200: return 5
    if r > 200 and g > 200 and b < 100: return 2
    if r > 200 and g < 100 and b > 200: return 6
    if r < 100 and g > 200 and b > 200: return 4
    return 7