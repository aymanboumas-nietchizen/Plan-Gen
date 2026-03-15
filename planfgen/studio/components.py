"""
studio/components.py
====================
Reusable UI components for the PLANFGEN Streamlit Studio.

Architectural-style floor plan rendering using Plotly SVG shapes:
- Room polygons (any shape) with light pastel fills
- Thick exterior walls with dark fill
- Interior walls as lines
- Door arc swings (quarter-circle)
- Window symbols on exterior walls
- Room labels with name + area
"""
from __future__ import annotations

import math
from typing import List, Tuple

import plotly.graph_objects as go
import streamlit as st

from planfgen.core.geometry import Envelope


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    """Convert '#rrggbb' to 'rgba(r,g,b,a)' for Plotly compatibility."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return f"rgba(128,128,128,{alpha})"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ---------------------------------------------------------------------------
# SVG path helpers
# ---------------------------------------------------------------------------

def _polygon_to_svg_path(coords: List[Tuple[float, float]]) -> str:
    """Convert [(x,y), ...] to Plotly SVG path string 'M x y L x y ... Z'."""
    if not coords:
        return ""
    parts = [f"M {coords[0][0]} {coords[0][1]}"]
    for x, y in coords[1:]:
        parts.append(f"L {x} {y}")
    parts.append("Z")
    return " ".join(parts)


def _wall_buffer_path(x0: float, y0: float, x1: float, y1: float,
                      thickness: float) -> str:
    """
    Build SVG path for a thick wall segment (filled rectangle offset
    perpendicular to the wall line).
    """
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return ""
    # Unit normal perpendicular to wall
    nx, ny = -dy / length, dx / length
    half = thickness / 2
    # Four corners of the wall rectangle
    ax, ay = x0 + nx * half, y0 + ny * half
    bx, by = x1 + nx * half, y1 + ny * half
    cx, cy = x1 - nx * half, y1 - ny * half
    ddx, ddy = x0 - nx * half, y0 - ny * half
    return f"M {ax} {ay} L {bx} {by} L {cx} {cy} L {ddx} {ddy} Z"


def _door_arc_path(cx: float, cy: float, width: float,
                   wall_x0: float, wall_y0: float,
                   wall_x1: float, wall_y1: float) -> str:
    """
    Build SVG path for a door arc swing (quarter-circle).
    The arc is drawn from the door edge, swinging into the room.
    """
    dx, dy = wall_x1 - wall_x0, wall_y1 - wall_y0
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return ""
    # Wall direction unit vector
    ux, uy = dx / length, dy / length
    # Normal (into room side)
    nx, ny = -uy, ux
    r = width * 0.9  # arc radius slightly less than door width
    # Door hinge point (one edge of the opening)
    hx = cx - ux * width / 2
    hy = cy - uy * width / 2
    # Arc end point (swung into room)
    ex = hx + nx * r
    ey = hy + ny * r
    # SVG arc: A rx ry x-rotation large-arc-flag sweep-flag x y
    return f"M {hx} {hy} A {r} {r} 0 0 1 {ex} {ey}"


def _window_shapes(cx: float, cy: float, width: float,
                   wall_x0: float, wall_y0: float,
                   wall_x1: float, wall_y1: float,
                   thickness: float = 0.30) -> List[dict]:
    """
    Return a list of Plotly shape dicts for a window symbol:
    two parallel lines perpendicular to wall + a gap.
    """
    dx, dy = wall_x1 - wall_x0, wall_y1 - wall_y0
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return []
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    half_w = width / 2
    half_t = thickness / 2

    shapes = []
    # Two parallel lines along wall direction at +/- half thickness
    for sign in (-1, 1):
        ox, oy = nx * half_t * sign, ny * half_t * sign
        shapes.append(dict(
            type="line",
            x0=cx - ux * half_w + ox, y0=cy - uy * half_w + oy,
            x1=cx + ux * half_w + ox, y1=cy + uy * half_w + oy,
            line=dict(color="#38bdf8", width=2),
        ))
    # Cross lines connecting the parallels (at ends and center)
    for t in (-half_w, 0, half_w):
        px, py = cx + ux * t, cy + uy * t
        shapes.append(dict(
            type="line",
            x0=px + nx * half_t, y0=py + ny * half_t,
            x1=px - nx * half_t, y1=py - ny * half_t,
            line=dict(color="#38bdf8", width=1.5),
        ))
    return shapes


# ---------------------------------------------------------------------------
# Main floor plan renderer
# ---------------------------------------------------------------------------

def render_floor_plan(
    placed: dict,
    envelope,
    adj_rules: list,
    wall_system=None,
    show_adj: bool = False,
    height: int = 400,
    mini: bool = False,
) -> go.Figure:
    """
    Render a floor plan as an architectural Plotly figure.

    Parameters
    ----------
    placed      : {nom: Room} layout dict
    envelope    : Envelope object (or float W for backward compat)
    adj_rules   : list of adjacency detail dicts
    wall_system : WallSystem from build_wall_system() (optional)
    show_adj    : draw adjacency lines
    height      : figure height in pixels
    mini        : simplified rendering for gallery thumbnails
    """
    fig = go.Figure()

    # Resolve envelope dimensions
    if isinstance(envelope, Envelope):
        W = envelope.W
        H = envelope.H
        env_coords = list(envelope.polygon.exterior.coords)
    else:
        # Backward compat: envelope is W float, use adj_rules context
        W = float(envelope)
        H = float(adj_rules[0]["_H"]) if adj_rules and "_H" in adj_rules[0] else 9.0
        env_coords = [(0, 0), (W, 0), (W, H), (0, H), (0, 0)]

    # ── 1. Background: envelope filled white ──────────────────────────────
    env_path = _polygon_to_svg_path(env_coords)
    fig.add_shape(
        type="path", path=env_path,
        fillcolor="#f8f9fa",
        line=dict(color="rgba(0,0,0,0)", width=0),
    )

    # ── 2. Room polygons (any shape) ──────────────────────────────────────
    for nom, room in placed.items():
        color = getattr(room, "color", "#cccccc")
        room_coords = list(room.polygon.exterior.coords)
        room_path = _polygon_to_svg_path(room_coords)

        fig.add_shape(
            type="path", path=room_path,
            fillcolor=_hex_to_rgba(color, 0.30),
            line=dict(color=_hex_to_rgba(color, 0.50), width=1),
        )

        # Room label (skip in mini mode)
        if not mini:
            fig.add_annotation(
                x=room.cx, y=room.cy,
                text=f"<b>{nom}</b><br>{room.area:.1f} m\u00b2",
                showarrow=False,
                font=dict(size=10, color="#1e293b"),
                align="center",
            )

    # ── 3. Walls ──────────────────────────────────────────────────────────
    if wall_system is not None:
        # Exterior walls: thick filled rectangles
        for wall in wall_system.walls:
            if wall.wall_type == "exterior":
                path = _wall_buffer_path(
                    wall.x0, wall.y0, wall.x1, wall.y1,
                    wall.thickness,
                )
                if path:
                    fig.add_shape(
                        type="path", path=path,
                        fillcolor="#374151",
                        line=dict(color="#1f2937", width=0.5),
                    )
            else:
                # Interior walls: thick filled rectangles (like exterior)
                int_path = _wall_buffer_path(
                    wall.x0, wall.y0, wall.x1, wall.y1,
                    wall.thickness,
                )
                if int_path:
                    fig.add_shape(
                        type="path", path=int_path,
                        fillcolor="#9ca3af",
                        line=dict(color="#6b7280", width=0.5 if not mini else 0.3),
                    )

        # Doors (skip arcs in mini mode)
        if not mini:
            for door in wall_system.doors:
                w = door.wall
                # Door arc
                arc_path = _door_arc_path(
                    door.cx, door.cy, door.width,
                    w.x0, w.y0, w.x1, w.y1,
                )
                if arc_path:
                    color_d = "#dc2626" if door.door_type == "entrance" else "#2563eb"
                    fig.add_shape(
                        type="path", path=arc_path,
                        line=dict(color=color_d, width=1.5),
                        fillcolor="rgba(0,0,0,0)",
                    )
                    # Small dot at door center
                    fig.add_shape(
                        type="circle",
                        x0=door.cx - 0.08, y0=door.cy - 0.08,
                        x1=door.cx + 0.08, y1=door.cy + 0.08,
                        fillcolor=color_d,
                        line=dict(color=color_d, width=0),
                    )

        # Windows (skip in mini mode)
        if not mini and hasattr(wall_system, "windows"):
            for win in wall_system.windows:
                w = win.wall
                for shape_dict in _window_shapes(
                    win.cx, win.cy, win.width,
                    w.x0, w.y0, w.x1, w.y1,
                    w.thickness,
                ):
                    fig.add_shape(**shape_dict)

    else:
        # No wall system: draw simple envelope border
        fig.add_shape(
            type="path", path=env_path,
            fillcolor="rgba(0,0,0,0)",
            line=dict(color="#6b7280", width=2, dash="dot"),
        )

    # ── 4. Adjacency lines ────────────────────────────────────────────────
    if show_adj and adj_rules and not mini:
        for rule in adj_rules:
            a, b = rule.get("a"), rule.get("b")
            ok = rule.get("ok", False)
            ra, rb = placed.get(a), placed.get(b)
            if ra and rb:
                color_line = "#22c55e" if ok else "#ef4444"
                fig.add_shape(
                    type="line",
                    x0=ra.cx, y0=ra.cy, x1=rb.cx, y1=rb.cy,
                    line=dict(color=color_line, width=2, dash="dash"),
                )

    # ── 5. Layout ─────────────────────────────────────────────────────────
    pad = 0.5
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=height,
        xaxis=dict(range=[-pad, W + pad], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(range=[-pad, H + pad], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="x"),
        paper_bgcolor="#e2e8f0",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return fig


# ---------------------------------------------------------------------------
# Score bar chart
# ---------------------------------------------------------------------------

def render_score_bar(scores: dict) -> go.Figure:
    """Horizontal bar chart of the 4 scoring metrics + global."""
    keys   = ["adjacences", "compacite", "facade", "couverture", "global"]
    labels = ["Adjacences", "Compacit\u00e9", "Fa\u00e7ade", "Couverture", "Global \u2605"]
    values = [scores.get(k, 0) for k in keys]
    colors = []
    for v in values:
        if v >= 0.85:   colors.append("#22c55e")
        elif v >= 0.70: colors.append("#f59e0b")
        else:           colors.append("#ef4444")

    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color=colors,
        text=[f"{v:.0%}" for v in values],
        textposition="outside",
        hovertemplate="%{y}: %{x:.2%}<extra></extra>",
    ))
    fig.update_layout(
        height=220, margin=dict(l=0, r=60, t=10, b=0),
        xaxis=dict(range=[0, 1.1], showgrid=False, visible=False),
        yaxis=dict(autorange="reversed"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"),
    )
    return fig


def medal(rank: int) -> str:
    return ["\U0001f947", "\U0001f948", "\U0001f949", "4\ufe0f\u20e3", "5\ufe0f\u20e3", "6\ufe0f\u20e3"][min(rank, 5)]
