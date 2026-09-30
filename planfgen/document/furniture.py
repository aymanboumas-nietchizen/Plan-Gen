"""L8 — how a piece of furniture is drawn on a plan, once, for every output.

The SVG preview, the DXF and the web studio all draw the same primitives, so a
bed has the same pillows everywhere. Primitives are in plan metres and are
plain tuples a JSON document can carry:

- ``("poly", [[x, y], ...])`` — a closed outline;
- ``("line", [x0, y0], [x1, y1])``;
- ``("circle", [cx, cy], r)``.

Drawn in each piece's own frame — across its width, and from its back to its
front — so a bed against the east wall has its pillows against the east wall.
"""

from __future__ import annotations

from planfgen.habitability.layout import Piece

Primitive = tuple

#: The DXF layer each category of piece is drawn on.
CATEGORY_LAYER: dict[str, str] = {
    "mobilier": "MOBILIER",
    "placard": "PLACARD",
    "sanitaire": "EQUIPEMENT",
    "cuisine": "EQUIPEMENT",
}


class _Frame:
    """(a, b) in the piece's frame -> plan metres. a across the front, centred;
    b from the back edge towards the front."""

    def __init__(self, piece: Piece):
        self.fx, self.fy = piece.facing
        self.ux, self.uy = self.fy, -self.fx
        self.bx, self.by = piece.insertion
        self.w, self.d = piece.width, piece.depth

    def at(self, a: float, b: float) -> list[float]:
        return [
            round(self.bx + self.ux * a + self.fx * b, 4),
            round(self.by + self.uy * a + self.fy * b, 4),
        ]

    def box(self, a0: float, b0: float, a1: float, b1: float) -> Primitive:
        return ("poly", [self.at(a0, b0), self.at(a1, b0), self.at(a1, b1), self.at(a0, b1)])

    def line(self, a0: float, b0: float, a1: float, b1: float) -> Primitive:
        return ("line", self.at(a0, b0), self.at(a1, b1))

    def circle(self, a: float, b: float, r: float) -> Primitive:
        return ("circle", self.at(a, b), round(r, 4))


def symbols(piece: Piece) -> list[Primitive]:
    """The drawing of one piece: its outline first, then its detail."""
    f = _Frame(piece)
    w, d = f.w, f.d
    h = w / 2
    out: list[Primitive] = [f.box(-h, 0, h, d)]
    key = piece.family

    if key.startswith("lit_"):
        pillows = 2 if w >= 1.30 else 1
        gap = 0.06
        pw = (w - gap * (pillows + 1)) / pillows
        for i in range(pillows):
            a0 = -h + gap + i * (pw + gap)
            out.append(f.box(a0, 0.06, a0 + pw, 0.36))
        out.append(f.line(-h, 0.55, h, 0.55))           # the sheet turned down
        out.append(f.line(-h, 0.55, -h + 0.25, 0.80))
    elif key == "placard_60":
        out.append(f.line(-h, d / 2, h, d / 2))          # the hanging rail
        n = max(2, int(w / 0.25))
        for i in range(1, n):
            a = -h + i * w / n
            out.append(f.line(a - 0.06, d / 2 - 0.18, a + 0.06, d / 2 + 0.18))
        out.append(f.line(-h, d - 0.03, h, d - 0.03))    # the sliding doors
    elif key in ("canape", "banquette"):
        out.append(f.line(-h, 0.20, h, 0.20))            # backrest
    elif key == "chaise":
        out.append(f.line(-h, 0.08, h, 0.08))
    elif key == "evier":
        out.append(f.box(-h + 0.08, 0.10, -h + 0.08 + min(0.50, w - 0.16), d - 0.08))
        out.append(f.circle(-h + 0.08 + min(0.25, (w - 0.16) / 2), d / 2, 0.03))
        if w >= 1.0:
            for i in range(4):                             # the drainer
                a = 0.05 + i * (h - 0.15) / 3
                out.append(f.line(a, 0.15, a, d - 0.12))
    elif key == "plaque_cuisson":
        for a, b, r in ((-0.14, 0.17, 0.09), (0.14, 0.17, 0.07),
                        (-0.14, 0.43, 0.07), (0.14, 0.43, 0.09)):
            out.append(f.circle(a, b, r))
    elif key == "refrigerateur":
        out.append(f.line(-h, 0, h, d))
        out.append(f.line(-h, d, h, 0))
    elif key == "meuble_bas_cuisine":
        out.append(f.line(-h, d - 0.04, h, d - 0.04))
    elif key == "baignoire":
        out.append(("poly", [f.at(-h + 0.07, 0.07), f.at(h - 0.07, 0.07),
                             f.at(h - 0.07, d - 0.07), f.at(-h + 0.07, d - 0.07)]))
        out.append(f.circle(-h + 0.22, d / 2, 0.035))
    elif key == "receveur_douche":
        out.append(f.line(-h, 0, h, d))
        out.append(f.line(-h, d, h, 0))
        out.append(f.circle(0, d / 2, 0.04))
    elif key in ("lavabo", "lave_mains"):
        out.append(f.circle(0, d * 0.55, min(w, d) * 0.32))
    elif key == "wc":
        out.append(f.box(-h, 0, h, 0.18))                # the cistern
        out.append(f.circle(0, 0.18 + (d - 0.18) * 0.52, min(h, (d - 0.18) / 2) * 0.95))
    elif key == "lave_linge":
        out.append(f.circle(0, d / 2, min(w, d) * 0.33))
    elif key == "table_basse" or key.startswith("table_manger"):
        pass
    elif key == "bureau":
        out.append(f.line(-h, d - 0.04, h, d - 0.04))
    elif key in ("etagere", "meuble_tv", "meuble_entree", "bac_a_laver", "chevet"):
        out.append(f.line(-h, d * 0.5, h, d * 0.5) if key == "etagere" else f.line(-h, 0.04, h, 0.04))
    return out


def furniture_document(furnished) -> list[dict]:
    """The `furniture` list of the bridge document: one entry per piece, carrying
    what a Revit add-in needs to place a family instance, and what the web page
    needs to draw it.

    ``family``    the stable key from `planfgen.habitability.layout.FAMILIES`
    ``width``, ``depth``, ``height``   the type parameters, metres
    ``insertion`` centre of the piece's back edge (on the wall face), metres
    ``rotation``  bearing of the piece's front, radians, 0 = north = +Y, clockwise
    ``facing``    the same as a unit vector [fx, fy]
    ``room``      the host room's `nom` (the `spaces[].nom` of the same document)
    """
    if furnished is None:
        return []
    out = []
    for piece in furnished.pieces:
        x0, y0, x1, y1 = piece.rect
        out.append(
            {
                "family": piece.family,
                "label": piece.label,
                "category": piece.category,
                "layer": CATEGORY_LAYER.get(piece.category, "MOBILIER"),
                "room": piece.room,
                "item": piece.item,
                "width": round(piece.width, 4),
                "depth": round(piece.depth, 4),
                "height": round(piece.height, 4),
                "insertion": [round(v, 4) for v in piece.insertion],
                "rotation": round(piece.rotation, 6),
                "facing": [round(v, 6) for v in piece.facing],
                "bbox": [round(v, 4) for v in (x0, y0, x1, y1)],
                "loose": piece.loose,
                "symbols": [list(p) for p in symbols(piece)],
            }
        )
    return out
