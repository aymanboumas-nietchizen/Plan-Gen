"""Studio — drawing the intermediate stages, so they can be told apart.

The point of the stage selector is that L1 and L3 are *not the same picture*.
v1 shipped one image and called it a plan; it was an organigramme, and there was
nothing to compare it against. Here the organigramme is drawn deliberately, as a
graph with no geometry in it at all, next to a plan drawn from real walls — and
the difference is the whole argument of the rewrite.

Pure string building, like `document/preview.py`.
"""

from __future__ import annotations

import math

from planfgen.document.preview import INK, PAPER, PALETTE, RULE
from planfgen.topology.relations import ProgrammeGraph, RelationType

#: How a relation is drawn. Colour, dash, and width.
RELATION_STYLE: dict[RelationType, tuple[str, str, float]] = {
    RelationType.CONNECTED: ("#1f2328", "none", 2.2),
    RelationType.ADJACENT: ("#3ecf8e", "none", 2.2),
    RelationType.NEAR: ("#94a3b8", "4 4", 1.4),
    RelationType.SEPARATED: ("#e11d48", "2 5", 1.6),
}

SIZE = 560.0
NODE_R = 34.0


def _ring(noms: list[str]) -> dict[str, tuple[float, float]]:
    """Rooms on a circle. Deterministic, and it makes every edge visible."""
    centre = SIZE / 2
    radius = centre - NODE_R - 26
    step = 2 * math.pi / max(1, len(noms))
    return {
        nom: (
            centre + radius * math.sin(i * step),
            centre - radius * math.cos(i * step),
        )
        for i, nom in enumerate(noms)
    }


def topology_svg(graph: ProgrammeGraph, programme=None) -> str:
    """L1 as what it is: a graph. No walls, no areas, no geometry.

    This is the drawing v1 produced and called a plan. Drawn on purpose here so
    it can be put beside L3 and seen for what it is.
    """
    noms = graph.noms or [r.nom for r in (programme.rooms if programme else [])]
    if not noms:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="80"></svg>'

    at = _ring(sorted(noms))
    kinds = {r.nom: r.kind for r in programme.rooms} if programme else {}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" '
        f'viewBox="0 0 {SIZE} {SIZE}" font-family="Inter, Segoe UI, sans-serif">',
        f'<rect width="100%" height="100%" fill="{PAPER}"/>',
    ]

    for relation in graph.relations:
        if relation.a not in at or relation.b not in at:
            continue
        (x0, y0), (x1, y1) = at[relation.a], at[relation.b]
        colour, dash, width = RELATION_STYLE[relation.kind]
        parts.append(
            f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
            f'stroke="{colour}" stroke-width="{width * relation.weight ** 0.5:.2f}" '
            f'stroke-dasharray="{dash}" opacity="0.75"/>'
        )

    for nom, (x, y) in at.items():
        colour = PALETTE.get(kinds.get(nom), "#cbd5e1")
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{NODE_R}" fill="{colour}" '
            f'fill-opacity="0.45" stroke="{INK}" stroke-width="1.1"/>'
        )
        label = nom if len(nom) <= 11 else nom[:10] + "…"
        parts.append(
            f'<text x="{x:.1f}" y="{y + 4:.1f}" font-size="11" text-anchor="middle" '
            f'fill="{INK}">{label}</text>'
        )

    parts.append(
        f'<text x="14" y="{SIZE - 14:.0f}" font-size="11" fill="{RULE}">'
        f"L1 — relations only. No wall has been drawn.</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts)


def partition_svg(plan, profile) -> str:
    """L2 as what it is: a tiling of axis rectangles, before any wall exists."""
    x0, y0, w, h = plan.envelope_rect
    margin = 48.0
    scale = min((SIZE - 2 * margin) / max(w, 1e-9), (SIZE - 2 * margin) / max(h, 1e-9))
    width = w * scale + 2 * margin
    height = h * scale + 2 * margin

    def px(x, y):
        return (margin + (x - x0) * scale, margin + (y0 + h - y) * scale)

    programme = plan.brief.programme
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
        f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'font-family="Inter, Segoe UI, sans-serif">',
        f'<rect width="100%" height="100%" fill="{PAPER}"/>',
    ]

    for cell in plan.cells:
        left, top = px(cell.x, cell.y + cell.h)
        colour = PALETTE.get(programme.by_nom(cell.nom).kind, "#cbd5e1")
        parts.append(
            f'<rect x="{left:.1f}" y="{top:.1f}" width="{cell.w * scale:.1f}" '
            f'height="{cell.h * scale:.1f}" fill="{colour}" fill-opacity="0.30" '
            f'stroke="{INK}" stroke-width="1.2"/>'
        )
        cx, cy = px(cell.x + cell.w / 2, cell.y + cell.h / 2)
        net = cell.net_area(profile)
        target = programme.by_nom(cell.nom).surface_utile
        parts.append(
            f'<text x="{cx:.1f}" y="{cy - 4:.1f}" font-size="12" font-weight="600" '
            f'text-anchor="middle" fill="{INK}">{cell.nom}</text>'
        )
        note = "band" if cell.is_band else f"{net:.2f} / {target:.2f}"
        parts.append(
            f'<text x="{cx:.1f}" y="{cy + 11:.1f}" font-size="10" '
            f'text-anchor="middle" fill="{INK}" opacity="0.7">{note}</text>'
        )

    parts.append(
        f'<text x="14" y="{height - 12:.0f}" font-size="11" fill="{RULE}">'
        f"L2 — cells on the axes: net / target. The walls are still nominal.</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts)
