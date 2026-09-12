"""L8 (early) — an SVG you can actually read a plan off.

Pure string building: no matplotlib, no external libraries, nothing to install
before you can look at what the engine produced. Walls are drawn as solids
rather than lines, because the whole point of v2 is that a wall has a thickness
and a room is what is left over — a preview drawn in hairlines would hide the
one thing worth checking.

Spaces are filled on their *net* polygon, so the coloured area on the page is
the habitable area in the stamp. If a fill and its walls ever leave a gap, the
solidification is wrong and you will see it.
"""

from __future__ import annotations

import math
from pathlib import Path

from shapely.geometry import Polygon

from planfgen.brief.programme import RoomType
from planfgen.fabric.plan import FabricPlan
from planfgen.fabric.solidify import wall_solids

#: Room colours, by kind. The preview owns these — a `Space` is derived from the
#: wall graph and has no business carrying a swatch.
PALETTE: dict[RoomType, str] = {
    RoomType.SEJOUR: "#4a9eff",
    RoomType.CHAMBRE: "#f1948a",
    RoomType.CHAMBRE_PRINCIPALE: "#f0a500",
    RoomType.CUISINE: "#3ecf8e",
    RoomType.SDB: "#c084fc",
    RoomType.WC: "#fb923c",
    RoomType.COULOIR: "#94a3b8",
    RoomType.ENTREE: "#94a3b8",
    RoomType.BUREAU: "#60a5fa",
    RoomType.CELLIER: "#a3a3a3",
    RoomType.TERRASSE: "#86efac",
}

INK = "#1f2328"
PAPER = "#fbfaf7"
RULE = "#8b8378"

MARGIN = 56.0
FOOTER = 64.0
TARGET_W = 1180.0
TARGET_H = 860.0


def _f(value: float, places: int = 2) -> str:
    return f"{value:.{places}f}".rstrip("0").rstrip(".") or "0"


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


class _View:
    """Plan metres to SVG pixels, with y flipped so north is up."""

    def __init__(self, bounds: tuple[float, float, float, float]):
        self.minx, self.miny, self.maxx, self.maxy = bounds
        span_x = max(self.maxx - self.minx, 1e-9)
        span_y = max(self.maxy - self.miny, 1e-9)
        self.scale = min(
            (TARGET_W - 2 * MARGIN) / span_x,
            (TARGET_H - 2 * MARGIN - FOOTER) / span_y,
        )
        self.width = span_x * self.scale + 2 * MARGIN
        self.height = span_y * self.scale + 2 * MARGIN + FOOTER

    def px(self, x: float, y: float) -> tuple[float, float]:
        return (
            MARGIN + (x - self.minx) * self.scale,
            MARGIN + (self.maxy - y) * self.scale,
        )

    def points(self, polygon: Polygon) -> str:
        return " ".join(
            f"{_f(px, 2)},{_f(py, 2)}"
            for px, py in (self.px(x, y) for x, y in polygon.exterior.coords[:-1])
        )


def _scale_bar(view: _View) -> list[str]:
    """A bar of a round number of metres, so the drawing can be measured."""
    span = view.maxx - view.minx
    length = next((n for n in (10.0, 5.0, 2.0, 1.0) if n <= span * 0.4), 1.0)
    px_len = length * view.scale
    x0 = MARGIN
    y0 = view.height - FOOTER + 22

    out = [
        f'<g stroke="{INK}" stroke-width="1.4" fill="none">',
        f'<path d="M{_f(x0,1)} {_f(y0,1)} h{_f(px_len,1)}"/>',
        f'<path d="M{_f(x0,1)} {_f(y0-5,1)} v10"/>',
        f'<path d="M{_f(x0+px_len,1)} {_f(y0-5,1)} v10"/>',
        f'<path d="M{_f(x0+px_len/2,1)} {_f(y0-3,1)} v6"/>',
        "</g>",
        f'<rect x="{_f(x0,1)}" y="{_f(y0-4,1)}" width="{_f(px_len/2,1)}" '
        f'height="8" fill="{INK}"/>',
        f'<text x="{_f(x0,1)}" y="{_f(y0+26,1)}" font-size="12" fill="{RULE}" '
        f'letter-spacing="0.06em">0</text>',
        f'<text x="{_f(x0+px_len,1)}" y="{_f(y0+26,1)}" font-size="12" '
        f'fill="{RULE}" text-anchor="middle" letter-spacing="0.06em">'
        f"{_f(length)} m</text>",
    ]
    return out


def _north_arrow(view: _View, north: float) -> list[str]:
    """North as the parcel knows it: a bearing clockwise from +Y."""
    cx = view.width - MARGIN - 26
    cy = view.height - FOOTER + 26
    dx, dy = math.sin(north), -math.cos(north)
    px, py = -dy, dx  # perpendicular, for the tail flare
    tip = (cx + dx * 22, cy + dy * 22)
    tail = (cx - dx * 16, cy - dy * 16)
    left = (tail[0] + px * 9, tail[1] + py * 9)
    right = (tail[0] - px * 9, tail[1] - py * 9)
    mid = (cx - dx * 5, cy - dy * 5)
    return [
        f'<circle cx="{_f(cx,1)}" cy="{_f(cy,1)}" r="30" fill="none" '
        f'stroke="{RULE}" stroke-width="1" opacity="0.5"/>',
        f'<polygon points="{_f(tip[0],1)},{_f(tip[1],1)} '
        f"{_f(left[0],1)},{_f(left[1],1)} {_f(mid[0],1)},{_f(mid[1],1)} "
        f'{_f(right[0],1)},{_f(right[1],1)}" fill="{INK}"/>',
        f'<text x="{_f(cx + dx * 40,1)}" y="{_f(cy + dy * 40 + 4,1)}" '
        f'font-size="13" font-weight="600" fill="{INK}" text-anchor="middle">N</text>',
    ]


def _stamp(view: _View, space, show: tuple[str, ...]) -> list[str]:
    """Name, net area and net dimensions, centred in the room."""
    net = space.net_polygon
    net_w, net_h = space.net_dims()
    cx, cy = view.px(net.centroid.x, net.centroid.y)
    px_w, px_h = net_w * view.scale, net_h * view.scale

    lines: list[tuple[str, int, int, float]] = []
    if "nom" in show:
        lines.append((_escape(space.nom), 14, 600, 1.0))
    if "net_area" in show:
        lines.append((f"{space.surface_utile:.2f} m²", 12, 400, 0.72))
    if "dims" in show:
        lines.append((f"{net_w:.2f} × {net_h:.2f}", 11, 400, 0.55))
    if not lines:
        return []

    # A corridor is narrow and long: turn the stamp along it rather than
    # dropping it, and keep only what will fit.
    rotate = px_h > px_w * 1.5 and px_w < 110
    across, along = (px_h, px_w) if rotate else (px_w, px_h)
    if across < 46 or along < 16:
        return []
    while lines and len(lines) * 15 > along:
        lines.pop()
    if not lines:
        return []

    transform = f' transform="rotate(-90 {_f(cx,1)} {_f(cy,1)})"' if rotate else ""
    top = cy - (len(lines) - 1) * 7.5
    out = [f'<g text-anchor="middle"{transform}>']
    for i, (text, size, weight, opacity) in enumerate(lines):
        out.append(
            f'<text x="{_f(cx,1)}" y="{_f(top + i * 15 + 4,1)}" font-size="{size}" '
            f'font-weight="{weight}" fill="{INK}" opacity="{opacity}">{text}</text>'
        )
    out.append("</g>")
    return out


def to_svg(
    fabric_plan: FabricPlan,
    path: str | Path,
    show: tuple[str, ...] = ("nom", "net_area", "dims"),
) -> str:
    """Render a plan and write it to `path`. Returns the SVG source."""
    parcel = fabric_plan.parcel
    view = _View(parcel.outline.bounds)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_f(view.width,1)}" '
        f'height="{_f(view.height,1)}" viewBox="0 0 {_f(view.width,1)} '
        f'{_f(view.height,1)}" font-family="Inter, Segoe UI, Helvetica, '
        f'Arial, sans-serif">',
        f'<rect width="100%" height="100%" fill="{PAPER}"/>',
        f'<polygon points="{view.points(parcel.outline)}" fill="none" '
        f'stroke="{RULE}" stroke-width="1.2" stroke-dasharray="7 5"/>',
    ]

    for space in fabric_plan.spaces.values():
        colour = PALETTE.get(space.kind, "#cbd5e1")
        parts.append(
            f'<polygon points="{view.points(space.net_polygon)}" fill="{colour}" '
            f'fill-opacity="0.30"/>'
        )

    parts.append(f'<g fill="{INK}">')
    for _wall, solid in wall_solids(fabric_plan.graph, fabric_plan.profile):
        parts.append(f'<polygon points="{view.points(solid)}"/>')
    parts.append("</g>")

    for space in fabric_plan.spaces.values():
        parts.extend(_stamp(view, space, show))

    parts.extend(_scale_bar(view))
    parts.extend(_north_arrow(view, parcel.north))
    parts.append("</svg>")

    svg = "\n".join(parts)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(svg, encoding="utf-8")
    return svg
