"""L7 — furnishing a plan: real pieces, placed, so the ergonomics can be seen.

`check.fits` asks whether one abstract clear rectangle fits a room. This module
answers the question an architect actually asks of a plan: *where does the bed
go?* Every room of a `FabricPlan` that has L6 openings gets its standard set of
pieces — beds, placards, a kitchen run, sanitary fittings — each an axis-aligned
rectangle placed against a wall, with the floor it needs in front of it to be
used, and nothing where a door swings or where a person has to walk.

It is not a gate (S31 measures it; see PROGRESS.md). It never changes a wall.

What "placed" means, and is tested for (`test_layout.py`):

- every piece lies inside its room's net rectangle;
- no two pieces overlap, and no piece stands in another's clearance;
- nothing stands in a door's square: the leaf's width by the leaf's depth, on
  BOTH faces of the wall — the swing on one side, the approach on the other;
- nothing taller than the window sill (`profile.allege_h`) stands in front of a
  window: a placard or a fridge may not blind the glass, a bed or a sink may;
- from every door of the room a person 0.60 m wide (to within the 5 cm grid)
  can walk to every other door of the room and into every piece's use zone;
- the same plan always gives the same furniture.

Placards are built-in: a niche drawn inside the room, counted in its area, never
a room of their own.

The search is a bounded depth-first over each room's required items, in the
order the table lists them, then the optional ones greedily. Candidates are the
four walls of the room, both hands, every 10 cm along the wall; each candidate
costs a handful of float comparisons, and only those that survive them pay for
the walkability flood (numpy, 5 cm grid, one room). No Shapely anywhere.

**Family keys.** Every piece carries a stable `family` key from `FAMILIES` —
the fixed vocabulary a Revit add-in maps onto the agency's own families. The
key, its type parameters (width, depth, height), an insertion point and a
rotation are everything needed to place a family instance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from planfgen.fabric.plan import FabricPlan

Rect = tuple[float, float, float, float]  # (x0, y0, x1, y1), metres

_EPS = 1e-6


# --- the vocabulary -------------------------------------------------------------


@dataclass(frozen=True)
class Family:
    """One kind of piece, as the agency's family library would know it.

    `width` is measured across the piece's front, `depth` from its back to its
    front, `height` off the floor. These are the family's *default* type
    parameters; a piece whose width varies (a placard, a worktop, a banquette)
    exports its own width and keeps the key.
    """

    key: str
    label: str
    category: str  # "mobilier" | "placard" | "sanitaire" | "cuisine"
    width: float
    depth: float
    height: float


def _family(key, label, category, width, depth, height) -> tuple[str, Family]:
    return key, Family(key, label, category, width, depth, height)


#: The fixed vocabulary of pieces. **Common practice, not regulation**: these are
#: ordinary Moroccan agency / Neufert dimensions for residential furniture and
#: fittings, chosen so a plan can be judged by eye. None of them is a legal
#: minimum and none belongs in `brief/regulation.py`. Change a number here and
#: every layout follows; change a KEY and the Revit mapping table breaks — keys
#: are append-only.
FAMILIES: dict[str, Family] = dict(
    [
        # sleeping
        _family("lit_double_160x200", "lit double 160x200", "mobilier", 1.60, 2.00, 0.50),
        _family("lit_double_140x190", "lit double 140x190", "mobilier", 1.40, 1.90, 0.50),
        _family("lit_simple_120x190", "lit 120x190", "mobilier", 1.20, 1.90, 0.50),
        _family("lit_simple_90x190", "lit simple 90x190", "mobilier", 0.90, 1.90, 0.50),
        _family("chevet", "chevet", "mobilier", 0.45, 0.40, 0.55),
        # storage
        _family("placard_60", "placard 60", "placard", 1.20, 0.60, 2.50),
        _family("meuble_entree", "meuble d'entree", "mobilier", 1.00, 0.35, 0.90),
        _family("etagere", "etagere", "mobilier", 0.90, 0.40, 1.80),
        # work
        _family("bureau", "bureau", "mobilier", 1.00, 0.55, 0.75),
        _family("chaise", "chaise", "mobilier", 0.45, 0.45, 0.90),
        # living
        _family("banquette", "banquette (salon marocain)", "mobilier", 2.00, 0.70, 0.80),
        _family("canape", "canape", "mobilier", 2.00, 0.85, 0.85),
        _family("table_basse", "table basse", "mobilier", 1.00, 0.55, 0.40),
        _family("table_manger_4", "table a manger 4 pers.", "mobilier", 1.20, 0.80, 0.75),
        _family("table_manger_6", "table a manger 6 pers.", "mobilier", 1.60, 0.90, 0.75),
        _family("meuble_tv", "meuble TV / rangement", "mobilier", 1.60, 0.45, 0.55),
        # kitchen
        _family("refrigerateur", "refrigerateur", "cuisine", 0.60, 0.60, 1.80),
        _family("meuble_bas_cuisine", "meuble bas / plan de travail", "cuisine", 0.60, 0.60, 0.90),
        _family("evier", "evier (meuble sous-evier)", "cuisine", 1.20, 0.60, 0.90),
        _family("plaque_cuisson", "plaque de cuisson (meuble)", "cuisine", 0.60, 0.60, 0.90),
        # sanitary
        _family("baignoire", "baignoire", "sanitaire", 1.70, 0.70, 0.55),
        _family("receveur_douche", "receveur de douche", "sanitaire", 0.90, 0.90, 0.10),
        _family("lavabo", "lavabo", "sanitaire", 0.60, 0.45, 0.85),
        _family("wc", "WC a reservoir", "sanitaire", 0.40, 0.70, 0.80),
        _family("lave_mains", "lave-mains", "sanitaire", 0.40, 0.25, 0.85),
        _family("lave_linge", "lave-linge", "sanitaire", 0.60, 0.60, 0.85),
        _family("bac_a_laver", "bac a laver", "sanitaire", 0.60, 0.50, 0.85),
    ]
)

#: A person, walking: the clear width kept from each door to each piece. Common
#: practice (a 0.60 m passage beside a bed or in front of a wardrobe).
PASSAGE = 0.60
#: Clear depth kept in front of a window for anything taller than the sill.
WINDOW_REACH = 0.60
#: Walkability grid step. The passage is checked to within one step.
GRID = 0.05
#: How far into a zone a walking person must be to use it, per axis.
REACH = 0.30


# --- items: what a room asks for, in the item's own frame -----------------------
#
# An item is placed against one wall. Its frame: x runs along the wall, y runs
# from the wall's face into the room. A `Part` is a piece of furniture; a `Zone`
# is floor the item needs clear. `use` zones must be walked into; the others
# must only be free. `loose` parts (chairs, a coffee table) stand inside their
# own item's zones and do not block the walk — they are pulled out of the way.


@dataclass(frozen=True)
class Part:
    family: str
    x: float
    y: float
    w: float  # extent along the wall, in the item frame
    d: float  # extent into the room, in the item frame
    face: str = "out"  # where the piece's front points: out | in | right | left
    loose: bool = False


@dataclass(frozen=True)
class Zone:
    x: float
    y: float
    w: float
    d: float
    use: bool = True


@dataclass(frozen=True)
class Variant:
    parts: tuple[Part, ...]
    zones: tuple[Zone, ...]
    corner: bool = False  # x = 0 must sit in a corner of the room

    def extent(self) -> tuple[float, float]:
        rects = [(p.x, p.y, p.x + p.w, p.y + p.d) for p in self.parts]
        rects += [(z.x, z.y, z.x + z.w, z.y + z.d) for z in self.zones]
        return max(r[2] for r in rects), max(r[3] for r in rects)


@dataclass(frozen=True)
class Item:
    nom: str
    variants: tuple[Variant, ...]
    optional: bool = False
    prefer: str = "corner"  # corner | centre
    away_from_door: bool = False
    head_not_under_window: bool = False


def _p(family: str, x: float = 0.0, y: float = 0.0, w: float | None = None,
       d: float | None = None, face: str = "out", loose: bool = False) -> Part:
    fam = FAMILIES[family]
    across, along = fam.width, fam.depth
    if face in ("right", "left"):
        across, along = along, across
    return Part(family, x, y, across if w is None else w, along if d is None else d, face, loose)


def _bed_double(family: str) -> Variant:
    fam = FAMILIES[family]
    w, l = fam.width, fam.depth
    ch = FAMILIES["chevet"]
    lane = PASSAGE
    inset = (lane - ch.width) / 2
    return Variant(
        parts=(
            _p("chevet", inset, 0.0),
            _p(family, lane, 0.0),
            _p("chevet", lane + w + inset, 0.0),
        ),
        zones=(
            Zone(0.0, ch.depth, lane, l - ch.depth),
            Zone(lane + w, ch.depth, lane, l - ch.depth),
            Zone(0.0, l, w + 2 * lane, PASSAGE, use=False),
        ),
    )


def _bed_single(family: str) -> tuple[Variant, ...]:
    fam = FAMILIES[family]
    w, l = fam.width, fam.depth
    head_on_wall = Variant(
        parts=(_p(family, 0.0, 0.0),),
        zones=(Zone(w, 0.0, PASSAGE, l),),
    )
    # Long side along the wall, head in the corner: the small-room arrangement.
    along_wall = Variant(
        parts=(_p(family, 0.0, 0.0, face="right"),),
        zones=(Zone(0.0, w, l, PASSAGE),),
        corner=True,
    )
    return head_on_wall, along_wall


def _placard(length: float) -> Variant:
    return Variant(
        parts=(_p("placard_60", 0.0, 0.0, w=length),),
        zones=(Zone(0.0, FAMILIES["placard_60"].depth, length, PASSAGE),),
    )


def _desk() -> Variant:
    desk, chair = FAMILIES["bureau"], FAMILIES["chaise"]
    return Variant(
        parts=(
            _p("bureau", 0.0, 0.0),
            _p("chaise", (desk.width - chair.width) / 2, desk.depth + 0.05, face="in", loose=True),
        ),
        zones=(Zone(0.0, desk.depth, desk.width, 0.75),),
    )


def _run(length: float) -> Variant:
    """A straight kitchen run: fridge at the end, sink, a worktop, the hob."""
    fridge, hob = FAMILIES["refrigerateur"], FAMILIES["plaque_cuisson"]
    sink = FAMILIES["evier"].width if length >= 3.0 else 0.80
    rest = length - fridge.width - sink - hob.width
    between = min(max(rest, 0.0), 0.60)
    rest -= between
    end = min(max(rest, 0.0), 0.30)
    before = max(rest - end, 0.0)
    parts, x = [], 0.0
    for family, width in (
        ("refrigerateur", fridge.width),
        ("meuble_bas_cuisine", before),
        ("evier", sink),
        ("meuble_bas_cuisine", between),
        ("plaque_cuisson", hob.width),
        ("meuble_bas_cuisine", end),
    ):
        if width > 1e-9:
            parts.append(_p(family, x, 0.0, w=width))
            x += width
    return Variant(parts=tuple(parts), zones=(Zone(0.0, 0.60, x, 1.10),))


def _worktop(length: float) -> Variant:
    return Variant(
        parts=(_p("meuble_bas_cuisine", 0.0, 0.0, w=length),),
        zones=(Zone(0.0, 0.60, length, 0.90),),
    )


def _salon_l(a: float, b: float) -> Variant:
    """Salon marocain: two banquettes in a corner, a low table in front."""
    deep = FAMILIES["banquette"].depth
    table = FAMILIES["table_basse"]
    return Variant(
        parts=(
            _p("banquette", 0.0, 0.0, w=a),
            _p("banquette", 0.0, deep, w=deep, d=b - deep, face="right"),
            _p("table_basse", deep + 0.45, deep + 0.45, loose=True),
        ),
        zones=(Zone(deep, deep, a - deep, max(b - deep, 1.30)),),
        corner=True,
    )


def _sofa(length: float) -> Variant:
    deep = FAMILIES["canape"].depth
    table = FAMILIES["table_basse"]
    return Variant(
        parts=(
            _p("canape", 0.0, 0.0, w=length),
            _p("table_basse", (length - table.width) / 2, deep + 0.40, loose=True),
        ),
        zones=(Zone(0.0, deep, length, 1.30),),
    )


def _table(family: str, free: bool) -> Variant:
    """A dining table and its chairs, with 0.75 m to pull a chair out on every
    seated side. `free`: standing clear of the wall, seated on its two long
    sides; otherwise its short end against the wall, seated on both sides."""
    fam = FAMILIES[family]
    chair = FAMILIES["chaise"]
    pull = 0.75
    if free:
        tw, td = fam.width, fam.depth
        parts = [_p(family, pull, pull)]
        seats = 3 if tw >= 1.50 else 2
        for i in range(seats):
            cx = pull + tw * (i + 0.5) / seats - chair.width / 2
            parts.append(_p("chaise", cx, pull - chair.depth, face="out", loose=True))
            parts.append(_p("chaise", cx, pull + td, face="in", loose=True))
        zone = Zone(0.0, 0.0, tw + 2 * pull, td + 2 * pull)
    else:
        tw, td = fam.depth, fam.width  # turned: short end to the wall
        parts = [_p(family, pull, 0.0, face="right")]
        seats = 2
        for j in range(seats):
            cy = td * (j + 0.5) / seats - chair.width / 2
            parts.append(_p("chaise", pull - chair.depth, cy, face="right", loose=True))
            parts.append(_p("chaise", pull + tw, cy, face="left", loose=True))
        zone = Zone(0.0, 0.0, tw + 2 * pull, td + PASSAGE)
    return Variant(parts=tuple(parts), zones=(zone,))


def _plain(family: str, clear: float, width: float | None = None,
           side: float = 0.0) -> Variant:
    """One piece against the wall, `clear` metres of floor in front of it, and
    `side` metres kept free each side of it (a WC's elbows)."""
    fam = FAMILIES[family]
    w = fam.width if width is None else width
    parts = (_p(family, side, 0.0, w=width),)
    zones = [Zone(0.0, fam.depth, w + 2 * side, clear)]
    if side > 0:
        zones += [Zone(0.0, 0.0, side, fam.depth, use=False),
                  Zone(side + w, 0.0, side, fam.depth, use=False)]
    return Variant(parts=parts, zones=tuple(zones))


def _bath(family: str, width: float | None = None) -> Variant:
    fam = FAMILIES[family]
    w = fam.width if width is None else width
    return Variant(
        parts=(_p(family, 0.0, 0.0, w=w),),
        zones=(Zone(0.0, fam.depth, w, 0.70),),
    )


_WC = _plain("wc", 0.60, side=0.20)

_PLACARD_MASTER = tuple(_placard(n) for n in (1.80, 1.50, 1.20))
_PLACARD_ROOM = tuple(_placard(n) for n in (1.50, 1.20))

#: What each room kind is furnished with, by `RoomType` NAME (so CELLIER and its
#: successor BUANDERIE read the same row). Required items first, in the order
#: they are placed; variants within an item largest first.
ROOM_ITEMS: dict[str, tuple[Item, ...]] = {
    "CHAMBRE_PRINCIPALE": (
        Item("lit double + chevets",
             (_bed_double("lit_double_160x200"), _bed_double("lit_double_140x190")),
             prefer="centre", away_from_door=True, head_not_under_window=True),
        Item("placard", _PLACARD_MASTER, prefer="corner"),
    ),
    "CHAMBRE": (
        Item("lit",
             _bed_single("lit_simple_120x190") + _bed_single("lit_simple_90x190"),
             prefer="corner", away_from_door=True, head_not_under_window=True),
        Item("placard", _PLACARD_ROOM, prefer="corner"),
        Item("bureau", (_desk(),), optional=True),
    ),
    "SEJOUR": (
        Item("salon",
             (_salon_l(2.60, 2.20), _salon_l(2.20, 1.80), _sofa(2.20), _sofa(1.80)),
             prefer="corner", away_from_door=True),
        Item("table a manger",
             (_table("table_manger_6", True), _table("table_manger_4", True),
              _table("table_manger_4", False)),
             prefer="centre"),
        Item("meuble TV / rangement",
             tuple(_plain("meuble_tv", PASSAGE, width=n) for n in (1.60, 1.20, 0.90)),
             prefer="centre"),
    ),
    "CUISINE": (
        Item("plan de travail", tuple(_run(n) for n in (3.60, 3.00, 2.40, 2.00)),
             prefer="corner"),
        Item("retour de plan", (_worktop(1.20), _worktop(0.90)), optional=True),
    ),
    "SDB": (
        Item("baignoire ou douche",
             (_bath("baignoire"), _bath("baignoire", 1.60),
              _bath("receveur_douche"), _bath("receveur_douche", 0.80)),
             prefer="corner"),
        Item("lavabo", (_plain("lavabo", 0.70),), prefer="centre"),
    ),
    "WC": (
        Item("WC", (_WC,), prefer="centre", away_from_door=True),
        Item("lave-mains", (_plain("lave_mains", 0.50),), optional=True),
    ),
    "ENTREE": (
        Item("placard d'entree",
             (_placard(1.20), _placard(1.00), _plain("meuble_entree", PASSAGE)),
             optional=True),
    ),
    "BUANDERIE": (
        Item("lave-linge", (_plain("lave_linge", 0.70),), prefer="corner"),
        Item("bac / etagere", (_plain("bac_a_laver", 0.70), _plain("etagere", PASSAGE)),
             optional=True),
    ),
    "BUREAU": (
        Item("bureau", (_desk(),), prefer="centre"),
        Item("etagere", (_plain("etagere", PASSAGE),), optional=True),
    ),
}
ROOM_ITEMS["CELLIER"] = ROOM_ITEMS["BUANDERIE"]

#: A bathroom takes the WC when the unit has no WC of its own.
SDB_WC = Item("WC", (_WC,), prefer="corner")


# --- results --------------------------------------------------------------------


@dataclass(frozen=True)
class Piece:
    """One placed piece: a family instance, and the rectangle it stands on.

    `rotation` is the bearing of the piece's front — the way a person using it
    faces it from, reversed — in radians, 0 = north = +Y, clockwise, as every
    angle in this project. `facing` is the same as a unit vector. `insertion` is
    the centre of the piece's back edge (on the wall face for a wall piece).
    """

    room: str
    item: str
    family: str
    label: str
    category: str
    rect: Rect
    width: float
    depth: float
    height: float
    rotation: float
    facing: tuple[float, float]
    insertion: tuple[float, float]
    loose: bool = False

    @property
    def center(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.rect
        return ((x0 + x1) / 2, (y0 + y1) / 2)


@dataclass(frozen=True)
class Missing:
    """An item that could not be placed, and why, in one line."""

    room: str
    item: str
    code: str  # too_small | doors | window | crowded | blocks_way | no_door
    reason: str
    optional: bool = False

    def __str__(self) -> str:
        return f"{self.room}: {self.item} — {self.reason}"


@dataclass
class RoomLayout:
    nom: str
    kind: str
    rect: Rect
    pieces: list[Piece] = field(default_factory=list)
    zones: list[Rect] = field(default_factory=list)
    keep_clear: list[Rect] = field(default_factory=list)  # door squares, in the room
    missing: list[Missing] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not any(not m.optional for m in self.missing)

    @property
    def doorless(self) -> bool:
        """No door or passage opens into this room, so no walk was checked:
        its furniture fits, but nobody was shown to reach it. An L6 fact."""
        return not self.keep_clear


@dataclass
class FurnishedPlan:
    """Every room's furniture, and everything that could not be placed."""

    rooms: dict[str, RoomLayout]

    @property
    def pieces(self) -> list[Piece]:
        return [p for room in self.rooms.values() for p in room.pieces]

    @property
    def missing(self) -> list[Missing]:
        """Required items that could not be placed."""
        return [m for room in self.rooms.values() for m in room.missing if not m.optional]

    @property
    def optional_missing(self) -> list[Missing]:
        return [m for room in self.rooms.values() for m in room.missing if m.optional]

    @property
    def complete(self) -> bool:
        return not self.missing

    @property
    def doorless(self) -> list[str]:
        """Furnished rooms no opening leads into (see `RoomLayout.doorless`)."""
        return [nom for nom, room in self.rooms.items() if room.doorless]

    def explain(self) -> str:
        head = f"{len(self.pieces)} pieces in {len(self.rooms)} rooms"
        tail = f"; no door into {', '.join(self.doorless)}" if self.doorless else ""
        if self.complete:
            return head + "; every room furnished" + tail
        return head + "; " + "; ".join(str(m) for m in self.missing) + tail


# --- geometry -------------------------------------------------------------------


def _overlap(a: Rect, b: Rect) -> bool:
    return a[0] < b[2] - _EPS and b[0] < a[2] - _EPS and a[1] < b[3] - _EPS and b[1] < a[3] - _EPS


def _inside(a: Rect, room: Rect) -> bool:
    return (a[0] >= room[0] - _EPS and a[1] >= room[1] - _EPS
            and a[2] <= room[2] + _EPS and a[3] <= room[3] + _EPS)


#: Room sides: which wall an item stands against, and how its frame maps onto
#: the plan. (origin corner, unit along the wall, unit into the room) — all four
#: are proper rotations, so a piece is never drawn mirror-imaged by a side.
_SIDES = ("S", "E", "N", "W")


def _frame(room: Rect, side: str) -> tuple[tuple[float, float], tuple[int, int], tuple[int, int], float]:
    x0, y0, x1, y1 = room
    if side == "S":
        return (x0, y0), (1, 0), (0, 1), x1 - x0
    if side == "N":
        return (x1, y1), (-1, 0), (0, -1), x1 - x0
    if side == "W":
        return (x0, y1), (0, -1), (1, 0), y1 - y0
    return (x1, y0), (0, 1), (-1, 0), y1 - y0  # E


def _to_plan(origin, u, v, t: float, x: float, y: float, w: float, d: float) -> Rect:
    ax = origin[0] + u[0] * (t + x) + v[0] * y
    ay = origin[1] + u[1] * (t + x) + v[1] * y
    bx = origin[0] + u[0] * (t + x + w) + v[0] * (y + d)
    by = origin[1] + u[1] * (t + x + w) + v[1] * (y + d)
    return (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))


_FACE = {"out": (0, 1), "in": (0, -1), "right": (1, 0), "left": (-1, 0)}


def _mirror(variant: Variant) -> Variant:
    width, _ = variant.extent()
    flip = {"right": "left", "left": "right"}
    return Variant(
        parts=tuple(
            Part(p.family, width - p.x - p.w, p.y, p.w, p.d, flip.get(p.face, p.face), p.loose)
            for p in variant.parts
        ),
        zones=tuple(Zone(width - z.x - z.w, z.y, z.w, z.d, z.use) for z in variant.zones),
        corner=variant.corner,
    )


@dataclass
class _Placed:
    """One placed item, in plan coordinates."""

    item: Item
    variant: Variant
    side: str
    t: float
    mirrored: bool
    bodies: list[tuple[Rect, Part]]
    zones: list[tuple[Rect, bool]]


def _place(item: Item, variant: Variant, mirrored: bool, room: Rect, side: str, t: float) -> _Placed:
    origin, u, v, _ = _frame(room, side)
    bodies = [(_to_plan(origin, u, v, t, p.x, p.y, p.w, p.d), p) for p in variant.parts]
    zones = [(_to_plan(origin, u, v, t, z.x, z.y, z.w, z.d), z.use) for z in variant.zones]
    return _Placed(item, variant, side, t, mirrored, bodies, zones)


# --- one room ------------------------------------------------------------------


@dataclass
class _Room:
    nom: str
    kind: str
    rect: Rect
    doors: list[Rect]  # squares kept clear in this room, one per opening
    windows: list[Rect]  # strips in front of windows, WINDOW_REACH deep
    fixed: list[Rect]  # shafts standing in the room
    door_sides: set[str]
    window_sides: set[str]
    tall: float  # anything higher than this may not stand in front of a window


def _side_of_room(room: Rect, wall, half: float) -> tuple[str, float, float] | None:
    """Which side of `room` the wall axis runs along, if it does, and the
    room's extent along it."""
    x0, y0, x1, y1 = room
    tol = 0.02
    if wall.is_horizontal:
        c = wall.p0[1]
        if abs(y0 - (c + half)) <= tol:
            return "S", x0, x1
        if abs(y1 - (c - half)) <= tol:
            return "N", x0, x1
        return None
    c = wall.p0[0]
    if abs(x0 - (c + half)) <= tol:
        return "W", y0, y1
    if abs(x1 - (c - half)) <= tol:
        return "E", y0, y1
    return None


def _strip(room: Rect, side: str, lo: float, hi: float, depth: float) -> Rect:
    x0, y0, x1, y1 = room
    depth = min(depth, (y1 - y0) if side in ("S", "N") else (x1 - x0))
    if side == "S":
        return (lo, y0, hi, y0 + depth)
    if side == "N":
        return (lo, y1 - depth, hi, y1)
    if side == "W":
        return (x0, lo, x0 + depth, hi)
    return (x1 - depth, lo, x1, hi)


def _opening_in(room: Rect, opening, width: float, depth: float, profile):
    """The (side, strip) an opening claims inside `room`, or None."""
    wall = opening.wall
    half = profile.thickness_of(wall.kind.value) / 2
    found = _side_of_room(room, wall, half)
    if found is None:
        return None
    side, lo_room, hi_room = found
    low, high = opening.span
    base = wall.p0[0] if wall.is_horizontal else wall.p0[1]
    lo, hi = max(base + low, lo_room), min(base + high, hi_room)
    if hi - lo <= 0.05:
        return None
    return side, _strip(room, side, lo, hi, depth)


def _room_context(fabric: FabricPlan, openings, shafts, nom: str) -> _Room:
    space = fabric.spaces[nom]
    rect = tuple(space.net_polygon.bounds)
    profile = fabric.profile
    doors, windows, door_sides, window_sides = [], [], set(), set()
    if openings is not None:
        for door in openings.doors:
            got = _opening_in(rect, door, door.leaf, door.leaf, profile)
            if got:
                door_sides.add(got[0])
                doors.append(got[1])
        for passage in getattr(openings, "passages", ()):
            got = _opening_in(rect, passage, passage.width, max(passage.width, PASSAGE), profile)
            if got:
                door_sides.add(got[0])
                doors.append(got[1])
        for window in openings.windows:
            got = _opening_in(rect, window, window.width, WINDOW_REACH, profile)
            if got:
                window_sides.add(got[0])
                windows.append(got[1])
    fixed = []
    for shaft in shafts or ():
        r = (shaft.x, shaft.y, shaft.x + shaft.w, shaft.y + shaft.h)
        if _overlap(r, rect):
            fixed.append((max(r[0], rect[0]), max(r[1], rect[1]),
                          min(r[2], rect[2]), min(r[3], rect[3])))
    return _Room(nom, space.kind.name, rect, doors, windows, fixed,
                 door_sides, window_sides, profile.allege_h)


def _blockers(room: _Room, cand: _Placed, placed: list[_Placed]) -> list[str]:
    """What stops this candidate, by name; empty if nothing does (walk aside)."""
    found: list[str] = []
    for rect, part in cand.bodies:
        if any(_overlap(rect, d) for d in room.doors):
            found.append("door")
        if FAMILIES[part.family].height > room.tall + _EPS and any(
            _overlap(rect, w) for w in room.windows
        ):
            found.append("window")
        if any(_overlap(rect, f) for f in room.fixed):
            found.append("shaft")
    for other in placed:
        rects = [r for r, _ in other.bodies] + [z for z, _ in other.zones]
        mine = [r for r, _ in cand.bodies]
        if any(_overlap(a, b) for a in mine for b in rects) or any(
            _overlap(z, r) for z, _ in cand.zones for r, _ in other.bodies
        ):
            found.append(other.item.nom)
    return found


def _fits_room(cand: _Placed, room: Rect) -> bool:
    return all(_inside(r, room) for r, _ in cand.bodies) and all(
        _inside(z, room) for z, _ in cand.zones
    )


def _candidates(item: Item, room: _Room):
    """Every placement of `item` inside the room, best first. Deterministic."""
    out = []
    for vi, base in enumerate(item.variants):
        for mirrored in (False, True):
            variant = _mirror(base) if mirrored else base
            width, depth = variant.extent()
            for si, side in enumerate(_SIDES):
                _, _, _, length = _frame(room.rect, side)
                span = length - width
                other = (room.rect[3] - room.rect[1]) if side in ("S", "N") else (room.rect[2] - room.rect[0])
                if span < -_EPS or depth > other + _EPS:
                    continue
                span = max(span, 0.0)
                if variant.corner:
                    spots = [span] if mirrored else [0.0]
                else:
                    n = int(span / 0.10 + 1e-9)
                    spots = sorted({0.0, span, span / 2, *(k * 0.10 for k in range(n + 1)),
                                    *(span - k * 0.10 for k in range(n + 1))})
                for t in spots:
                    if item.prefer == "centre":
                        score = abs(t - span / 2)
                    else:
                        score = min(t, span - t)
                    if item.away_from_door and side in room.door_sides:
                        score += 2.0
                    if item.head_not_under_window and side in room.window_sides:
                        score += 3.0
                    out.append(((vi, round(score, 6), si, mirrored, round(t, 6)),
                                variant, mirrored, side, t))
    out.sort(key=lambda c: c[0])
    for _, variant, mirrored, side, t in out:
        yield _place(item, variant, mirrored, room.rect, side, t)


# --- walking -------------------------------------------------------------------


class _Walk:
    """Where a 0.60 m person can stand in a room, and where they can get to."""

    def __init__(self, room: _Room, placed: list[_Placed]):
        x0, y0, x1, y1 = room.rect
        self.x0, self.y0 = x0, y0
        self.nx = max(1, int((x1 - x0) / GRID + 1e-9))
        self.ny = max(1, int((y1 - y0) / GRID + 1e-9))
        self.k = max(1, int(round(PASSAGE / GRID)) - 1)
        cx = x0 + (np.arange(self.nx) + 0.5) * GRID
        cy = y0 + (np.arange(self.ny) + 0.5) * GRID
        occupied = np.zeros((self.nx, self.ny), dtype=bool)
        solid = list(room.fixed) + [r for p in placed for r, part in p.bodies if not part.loose]
        for a, b, c, d in solid:
            ix = (cx > a) & (cx < c)
            iy = (cy > b) & (cy < d)
            occupied |= np.outer(ix, iy)
        k = self.k
        px, py = self.nx - k + 1, self.ny - k + 1
        if px <= 0 or py <= 0:
            self.free = np.zeros((0, 0), dtype=bool)
            return
        s = np.zeros((self.nx + 1, self.ny + 1), dtype=np.int32)
        s[1:, 1:] = occupied.cumsum(0).cumsum(1)
        block = s[k:, k:] - s[:-k, k:] - s[k:, :-k] + s[:-k, :-k]
        self.free = block == 0

    def touching(self, zone: Rect) -> np.ndarray:
        """Positions whose person square reaches REACH into `zone` on both axes."""
        if self.free.size == 0:
            return self.free
        a, b, c, d = zone
        size = self.k * GRID
        lx = self.x0 + np.arange(self.free.shape[0]) * GRID
        ly = self.y0 + np.arange(self.free.shape[1]) * GRID
        ox = np.minimum(lx + size, c) - np.maximum(lx, a)
        oy = np.minimum(ly + size, d) - np.maximum(ly, b)
        need_x = min(REACH, c - a) - 1e-6
        need_y = min(REACH, d - b) - 1e-6
        return np.outer(ox >= need_x, oy >= need_y)

    def reach(self, seeds: np.ndarray) -> np.ndarray:
        reached = seeds & self.free
        if not reached.any():
            return reached
        while True:
            grown = reached.copy()
            grown[1:, :] |= reached[:-1, :]
            grown[:-1, :] |= reached[1:, :]
            grown[:, 1:] |= reached[:, :-1]
            grown[:, :-1] |= reached[:, 1:]
            grown &= self.free
            if np.array_equal(grown, reached):
                return reached
            reached = grown


def _walkable(room: _Room, placed: list[_Placed]) -> bool:
    """Every door of the room joined to every other, and every use zone reached."""
    if not room.doors:
        return True
    walk = _Walk(room, placed)
    if walk.free.size == 0:
        return False
    reached = walk.reach(walk.touching(room.doors[0]))
    if not reached.any():
        return False
    for door in room.doors[1:]:
        if not (reached & walk.touching(door)).any():
            return False
    for p in placed:
        for zone, use in p.zones:
            if use and not (reached & walk.touching(zone)).any():
                return False
    return True


# --- the search ----------------------------------------------------------------

#: Walk floods a room may spend. Bounds the cost of a room nothing fits in.
_BUDGET = 400
#: Placements tried per item before backing up to the item before it.
_BRANCH = 8


class _Search:
    def __init__(self, room: _Room):
        self.room = room
        self.spent = 0
        self.best: list[_Placed] = []

    def _ok(self, cand: _Placed, placed: list[_Placed]) -> bool:
        return _fits_room(cand, self.room.rect) and not _blockers(self.room, cand, placed)

    def _walk_ok(self, placed: list[_Placed]) -> bool:
        self.spent += 1
        return _walkable(self.room, placed)

    def required(self, items: list[Item], placed: list[_Placed]) -> list[_Placed] | None:
        if len(placed) > len(self.best):
            self.best = list(placed)
        if not items:
            return placed
        item, rest = items[0], items[1:]
        tried = 0
        for cand in _candidates(item, self.room):
            if self.spent >= _BUDGET or tried >= _BRANCH:
                break
            if not self._ok(cand, placed):
                continue
            tried += 1
            trial = placed + [cand]
            if not self._walk_ok(trial):
                continue
            done = self.required(rest, trial)
            if done is not None:
                return done
        return None

    def optional(self, item: Item, placed: list[_Placed]) -> _Placed | None:
        tried = 0
        for cand in _candidates(item, self.room):
            if tried >= _BRANCH * 2:
                break
            if not self._ok(cand, placed):
                continue
            tried += 1
            if self._walk_ok(placed + [cand]):
                return cand
        return None


def _why(room: _Room, item: Item, placed: list[_Placed]) -> tuple[str, str]:
    """(code, reason) for an item that could not be placed next to `placed`."""
    x0, y0, x1, y1 = room.rect
    small = item.variants[-1]
    width, depth = small.extent()
    if not any(
        _fits_room(c, room.rect) for c in _candidates(Item(item.nom, (small,)), room)
    ):
        return "too_small", (
            f"needs {width:.2f} x {depth:.2f} m with its clearance, the room is "
            f"{x1 - x0:.2f} x {y1 - y0:.2f}"
        )
    fewest: list[str] | None = None
    for cand in _candidates(item, room):
        if not _fits_room(cand, room.rect):
            continue
        blockers = sorted(set(_blockers(room, cand, placed)))
        if not blockers:
            return "blocks_way", "every free position cuts the way from the door"
        if fewest is None or len(blockers) < len(fewest):
            fewest = blockers
    fewest = fewest or []
    words = {"door": "door swing", "window": "window", "shaft": "shaft"}
    named = [words.get(b, f"the {b}") for b in fewest]
    if set(fewest) <= {"door", "window", "shaft"}:
        code = "window" if fewest == ["window"] else "doors"
    else:
        code = "crowded"
    return code, f"no {width:.2f} m of wall free of " + " and ".join(named)


def _pieces(nom: str, placed: list[_Placed]) -> list[Piece]:
    out = []
    for p in placed:
        origin, u, v, _ = _frame((0, 0, 0, 0), p.side)
        for rect, part in p.bodies:
            fam = FAMILIES[part.family]
            fx, fy = _FACE[part.face]
            gx, gy = u[0] * fx + v[0] * fy, u[1] * fx + v[1] * fy
            x0, y0, x1, y1 = rect
            if gx == 0:
                width, depth = x1 - x0, y1 - y0
            else:
                width, depth = y1 - y0, x1 - x0
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            back = (cx - gx * depth / 2, cy - gy * depth / 2)
            rotation = math.atan2(gx, gy) % (2 * math.pi)
            out.append(
                Piece(
                    room=nom, item=p.item.nom, family=part.family, label=fam.label,
                    category=fam.category, rect=rect,
                    width=round(width, 4), depth=round(depth, 4), height=fam.height,
                    rotation=rotation, facing=(float(gx), float(gy)),
                    insertion=(round(back[0], 6), round(back[1], 6)), loose=part.loose,
                )
            )
    return out


def items_for(kind: str, has_wc: bool) -> tuple[Item, ...]:
    """The items a room of this kind is furnished with, in placement order."""
    items = ROOM_ITEMS.get(kind, ())
    if kind == "SDB" and not has_wc:
        items = items[:1] + (SDB_WC,) + items[1:]
    return items


def furnish_room(room: _Room, items: tuple[Item, ...]) -> RoomLayout:
    layout = RoomLayout(room.nom, room.kind, room.rect, keep_clear=list(room.doors))
    required = [i for i in items if not i.optional]
    search = _Search(room)
    placed = search.required(required, []) if required else []
    if placed is None:
        placed = search.best
        got = {p.item.nom for p in placed}
        for item in required:
            if item.nom in got:
                continue
            code, reason = _why(room, item, placed)
            if not room.doors and code == "blocks_way":
                code = "no_door"
            layout.missing.append(Missing(room.nom, item.nom, code, reason))
    for item in items:
        if not item.optional:
            continue
        cand = search.optional(item, placed)
        if cand is None:
            code, reason = _why(room, item, placed)
            layout.missing.append(Missing(room.nom, item.nom, code, reason, optional=True))
        else:
            placed = placed + [cand]
    layout.pieces = _pieces(room.nom, placed)
    layout.zones = [z for p in placed for z, _ in p.zones]
    return layout


def furnish(fabric: FabricPlan, openings=None, shafts=()) -> FurnishedPlan:
    """Furnish every room of a plan. Works on any unit: it reads only the
    plan's own spaces and openings, never the parcel or the building."""
    kinds = {space.kind.name for space in fabric.spaces.values()}
    has_wc = "WC" in kinds
    rooms: dict[str, RoomLayout] = {}
    for nom in sorted(fabric.spaces):
        room = _room_context(fabric, openings, shafts, nom)
        items = items_for(room.kind, has_wc)
        if not items:
            continue
        rooms[nom] = furnish_room(room, items)
    return FurnishedPlan(rooms)
