"""Beside the stack — `search/construct.py`: build trees the walk cannot reach.

The annealer mutates a tree one move at a time, and on real programmes the
valid plans are isolated: around a hand-built F3 one furniture miss from
passing, 0 of 341 one-move and 3 of 34 505 two-move neighbours pass every gate
(PROGRESS.md S27). A room behind a room, or a cluster round a degagement, is
not something a walk slides into. It has to be *built*.

Realise is top-down, and a subtree's rectangle depends only on WHICH rooms are
below it, so buildability decomposes. A region is (rooms, rectangle, the
thickness of each side's wall, what runs along each side, how many bands it
must hold, what the hub owes an ancestor); it is buildable iff it is one room
that furnishes and touches circulation over a door's width, or a cut or band
splits it into two buildable regions. `Constructor` is a randomised depth-first
search over that recursion, remembering dead regions.

What it returns is a *seed*, not a plan. Everything this local model does not
see — dead-end runs, the wall graph, the refinement passes of `realise`, a hub
without frontage in the fabric's sense — is left to the real gates, which every
constructed tree must still pass. Walls stay authored: the output is a slicing
tree like any other, realised by `SlicingTree.realise`.

Speed is part of the contract. Rooms are bitmasks with precomputed area sums;
each room's furniture is a closed-form window on its depth rather than a
`SpaceCell` to build; the split masks are drawn lazily in random order, and a
split is only descended once both halves pass the cheap tests; dead regions are
remembered across calls, live ones within a call.
"""

from __future__ import annotations

import math
import random

from planfgen.brief.plan import Brief
from planfgen.brief.programme import RoomType
from planfgen.fabric.axis import WallKind
from planfgen.fabric.plan import junction_module
from planfgen.habitability.furniture import FURNITURE
from planfgen.openings.window import DAYLIGHT_KINDS, width_owed, window_capacity
from planfgen.partition.tree import BAND_WALL, BandCut, Cut, Direction, Leaf, SlicingTree

SIDES = ("left", "right", "bottom", "top")

#: What runs along a region's side: a corridor band, the street, the hub,
#: facade a window may pierce (the daylight gate, decret ART. 7), and the
#: unit's exterior — where a corridor may not end, nothing being there to open.
BAND, STREET, HALL, LIGHT, EXT = 1, 2, 4, 8, 16
CIRC = BAND | HALL
KEEP = CIRC | LIGHT | EXT

#: `oblig`: none, else 0-3 the hub must TOUCH that side, 4-7 it must SPAN it.
FREE = -1

#: Metres to which a region's extent is rounded when it is remembered.
QUANTUM = 0.02

#: Relative slack on the cheap necessary conditions, so they never prune a
#: buildable region. The leaf test is the exact furniture gate.
SLACK = 0.03

#: Default effort. `CALLS` bounds one `find`; a find that exhausts its region
#: without running out proves the budget unbuildable and every later find at
#: that budget returns at once. Measured 2026-09-29, see PROGRESS.md S28.
TRIES = 6
CALLS = 20_000

_INF = math.inf
_EPS = 1e-9


class _OutOfCalls(Exception):
    """The call budget of one `find` is spent."""


def depth_windows(area: float, kind: RoomType, slack: float = 0.0) -> tuple[tuple[float, float], ...]:
    """The depths `p` at which a room of `area` m2 can hold its furniture.

    With `q = area / p` the other side: `min(p, q) >= min_side` gives
    `min_side <= p <= area / min_side`; the ratio gives
    `sqrt(area / R) <= p <= sqrt(R * area)`; and `max(p, q) >= min_long` holds
    for `p >= min_long` or `p <= area / min_long`. At most two intervals.
    `slack` relaxes the minima downward and the ratio upward.
    """
    spec = FURNITURE.get(kind)
    if spec is None:
        return ((0.0, _INF),)
    ms = spec.min_side * (1 - slack)
    ml = spec.min_long * (1 - slack)
    ratio = spec.max_ratio * (1 + slack) if spec.max_ratio is not None else None
    lo, hi = ms, area / ms
    if ratio is not None:
        lo, hi = max(lo, math.sqrt(area / ratio)), min(hi, math.sqrt(ratio * area))
    out = []
    for a, b in ((lo, min(hi, area / ml)), (max(lo, ml), hi)):
        if a <= b + _EPS:
            out.append((a, b))
    if len(out) == 2 and out[0][1] >= out[1][0] - _EPS:
        out = [(out[0][0], max(out[0][1], out[1][1]))]
    return tuple(out)


def _meets(windows, lo: float, hi: float) -> bool:
    return any(a <= hi + _EPS and lo <= b + _EPS for a, b in windows)


class Constructor:
    """Randomised depth-first construction of trees whose rooms furnish and are served.

    The hub is the room the front door opens into and which may be walked
    through: the ENTREE, or failing one the SEJOUR. A band whose ends meet no
    circulation is *floating* and the hub, somewhere below it, must meet it; a
    cut may declare one side of a sibling to be the hub, and the hub then owes
    that sibling the whole side. Both are carried down as `oblig`.

    Two circulation spaces join over `junction_module` of wall (a T-junction is
    an open passage); a room needs its own door, `door_module_for(kind)`. A
    room the law lights (`DAYLIGHT_KINDS`) needs enough openable facade for its
    windows — the daylight gate, asked of the leaf with the same arithmetic.
    """

    def __init__(
        self,
        brief: Brief,
        rect: tuple[float, float, float, float],
        entry_side: str | None = None,
        open_sides: frozenset[str] | None = None,
    ):
        """`rect` is the unit's envelope on the wall axes, `entry_side` the
        side of it the front door is on ("left", "right", "bottom", "top"), and
        `open_sides` the sides that may take windows.

        All are parameters rather than read off the parcel because a unit is
        not always the building: on a floor plate the envelope is set by the
        plate, the front door opens off a landing, not the street, and a side
        against a neighbouring flat or the stair core is blind. The defaults
        are the single-flat case — the parcel's entry edge and its openable
        segments (`Parcel.open_sides`).
        """
        prof = brief.profile
        programme = brief.programme
        self.rect = rect
        rooms = sorted(programme.rooms, key=lambda r: r.nom)
        rooms = [r for r in rooms if not r.kind.names_band]
        self.noms = tuple(r.nom for r in rooms)
        self.n = len(rooms)
        self.leaves = tuple(Leaf(nom) for nom in self.noms)
        kind = [r.kind for r in rooms]
        areas = [r.surface_utile for r in rooms]

        hub = next((i for i, k in enumerate(kind) if k is RoomType.ENTREE), None)
        if hub is None:
            hub = next((i for i, k in enumerate(kind) if k is RoomType.SEJOUR), None)
        self.hub = hub
        self.hub_bit = 0 if hub is None else 1 << hub

        # exact furniture, closed form: (min_side, min_long, max_ratio, min_area)
        self.exact = []
        for k in kind:
            spec = FURNITURE.get(k)
            self.exact.append((
                spec.min_side if spec else 0.0,
                spec.min_long if spec else 0.0,
                spec.max_ratio if spec and spec.max_ratio is not None else _INF,
                prof.min_area.get(k) or 0.0,
            ))
        self.windows = [depth_windows(a, k, SLACK) for a, k in zip(areas, kind)]
        self.area = areas

        if entry_side is None:
            entry_side = brief.parcel.side_of(brief.parcel.entry_edge)
        self.street = SIDES.index(entry_side)
        if open_sides is None:
            open_sides = brief.parcel.open_sides()
        self.open = tuple(side in open_sides for side in SIDES)
        self.prof = prof
        self.lit = [k in DAYLIGHT_KINDS for k in kind]
        self.lit_bits = sum(1 << i for i, k in enumerate(kind) if k in DAYLIGHT_KINDS)
        self.jn = junction_module(prof)
        # The run each room needs: off a band, its own door; off the hub, its
        # own door if the hub is a hall, the wider of the two if it is a room.
        hub_circ = hub is not None and kind[hub].is_circulation
        own = [prof.door_module_for(k) for k in kind]
        self.dm_band = own
        self.dm_hall = [m if hub_circ or hub is None else max(m, own[hub]) for m in own]
        # And what the hub needs to meet a floating band.
        self.hub_meets = self.jn if hub_circ or hub is None else own[hub]
        self.t_cloison = prof.thickness_of(WallKind.CLOISON.value)
        self.t_band = prof.thickness_of(BAND_WALL.value)
        self.t_facade = prof.thickness_of(WallKind.FACADE.value)
        self.clear = prof.corridor_clear

        self._sums: dict[int, float] = {0: 0.0}
        self.dead: set = set()
        self.calls = 0
        self.max_calls = 0
        self._alive: dict = {}

    # --- public -----------------------------------------------------------
    def find(self, rng: random.Random, budget: int, max_calls: int = CALLS) -> SlicingTree | None:
        """One tree with exactly `budget` bands, or None (none exists, or out of calls)."""
        if self.n == 0 or budget > max(0, self.n - 1):
            return None
        self.calls, self.max_calls = 0, max_calls
        self._alive = {}
        t = (self.t_facade,) * 4
        flags = self._outer_flags()
        x, y, w, h = self.rect
        state = ((1 << self.n) - 1, x, y, w, h, t, flags, budget, FREE)
        try:
            found = self._find(state, rng)
        except _OutOfCalls:
            return None
        if found is None or found[1] or found[2]:
            return None
        return SlicingTree(found[0])

    def proven_empty(self, budget: int) -> bool:
        """True once a find at `budget` has exhausted the whole search."""
        x, y, w, h = self.rect
        t = (self.t_facade,) * 4
        flags = self._outer_flags()
        return self._key(((1 << self.n) - 1, x, y, w, h, t, flags, budget, FREE)) in self.dead

    def _outer_flags(self) -> tuple[int, ...]:
        """What runs along each side of the whole unit: the street, light, and
        the exterior itself."""
        return tuple(
            EXT | (STREET if i == self.street else 0) | (LIGHT if self.open[i] else 0)
            for i in range(4)
        )

    # --- the local model ----------------------------------------------------
    def _sum(self, mask: int) -> float:
        s = self._sums.get(mask)
        if s is None:
            low = mask & -mask
            s = self.area[low.bit_length() - 1] + self._sum(mask ^ low)
            self._sums[mask] = s
        return s

    @staticmethod
    def _key(state):
        mask, _x, _y, w, h, t, flags, budget, oblig = state
        return (mask, round(w / QUANTUM), round(h / QUANTUM), t, flags, budget, oblig)

    def _leaf_ok(self, i: int, w: float, h: float, t, flags, oblig: int) -> bool:
        """The room furnishes, is lit, and is served: off a band or the hub,
        or — pending, settled where its region meets its sibling — through
        the end of a corridor on a side that is not the exterior."""
        return self._leaf_fit(i, w, h, t, flags, oblig) and (
            i == self.hub or self._served(i, w, h, flags) or bool(self._pending(i, w, h, flags)))

    def _served(self, i: int, w: float, h: float, flags) -> bool:
        band, hall = self.dm_band[i] - _EPS, self.dm_hall[i] - _EPS
        for side, f in enumerate(flags):
            run = h if side < 2 else w
            if (f & BAND and run >= band) or (f & HALL and run >= hall):
                return True
        return False

    def _pending(self, i: int, w: float, h: float, flags) -> tuple[int, ...]:
        """Interior sides a corridor's end could serve this room through."""
        need = self.dm_band[i] - _EPS
        if need > self.clear + self.t_band:
            return ()
        return tuple(s for s in range(4) if not flags[s] & EXT and (h if s < 2 else w) >= need)

    def _leaf_fit(self, i: int, w: float, h: float, t, flags, oblig: int) -> bool:
        nw = w - (t[0] + t[1]) / 2
        nh = h - (t[2] + t[3]) / 2
        short, long = (nw, nh) if nw <= nh else (nh, nw)
        ms, ml, ratio, minimum = self.exact[i]
        if short <= 0 or short < ms or long < ml or long > ratio * short:
            return False
        if nw * nh < minimum:
            return False
        if self.lit[i]:
            got = 0.0
            for side, f in enumerate(flags):
                if f & LIGHT:
                    got += window_capacity(nw if side >= 2 else nh, self.prof)
            if got < width_owed(nw * nh, self.prof) - _EPS:
                return False
        if i == self.hub:
            if not flags[self.street] & STREET:
                return False
            if oblig == FREE or oblig >= 4:
                return True
            return (h if oblig < 2 else w) >= self.hub_meets - _EPS
        return True

    def _plausible(self, mask: int, w: float, h: float, t, flags, budget: int, oblig: int) -> bool:
        nw = w - (t[0] + t[1]) / 2
        nh = h - (t[2] + t[3]) / 2
        if nw <= 0 or nh <= 0:
            return False
        if budget > bin(mask).count("1") - 1:
            return False
        if mask & self.lit_bits and not any(f & LIGHT for f in flags):
            return False                          # a room the law lights, and no window
        hi = nw * (1 + SLACK)
        m = mask
        while m:
            low = m & -m
            i = low.bit_length() - 1
            m ^= low
            if not _meets(self.windows[i], self.area[i] / nh * (1 - SLACK), hi):
                return False
        if not mask & self.hub_bit:
            if oblig != FREE:
                return False
            served = [s for s in range(4) if flags[s] & CIRC]
            if not served and all(f & EXT for f in flags):
                return False
            if budget == 0 and len(served) == 1:
                depth = nw if served[0] < 2 else nh      # every room a slab across
                m = mask
                while m:
                    low = m & -m
                    i = low.bit_length() - 1
                    m ^= low
                    if not _meets(self.windows[i], depth, depth):
                        return False
        return True

    def _check(self, state) -> bool:
        """Cheap test of a child region: leaf gate, memo, plausibility."""
        mask, _x, _y, w, h, t, flags, budget, oblig = state
        if mask & (mask - 1) == 0:
            if budget:
                return False
            return self._leaf_ok(mask.bit_length() - 1, w, h, t, flags, oblig)
        if self._key(state) in self.dead:
            return False
        return self._plausible(mask, w, h, t, flags, budget, oblig)

    def _options(self, state, low: int, high: int, rng: random.Random) -> list:
        """Every way to split `state` into `low` and `high` rooms, shuffled."""
        mask, x, y, w, h, t, flags, budget, oblig = state
        hub_bit = self.hub_bit
        h_low, h_high = bool(low & hub_bit), bool(high & hub_bit)
        d_low = self._sum(low)
        share = d_low / (d_low + self._sum(high))
        o_side = oblig % 4 if oblig != FREE else None
        o_span = oblig >= 4
        low_is_hub = h_low and low == hub_bit
        high_is_hub = h_high and high == hub_bit
        n_low, n_high = bin(low).count("1"), bin(high).count("1")
        out = []
        for d in (Direction.V, Direction.H):
            if d is Direction.V:
                lo_s, hi_s, a0, a1, e0, e1, extent = 1, 0, 0, 1, 2, 3, w
            else:
                lo_s, hi_s, a0, a1, e0, e1, extent = 3, 2, 2, 3, 0, 1, h
            inherited = (FREE, FREE)
            if o_side is not None:
                if o_span and o_side in (e0, e1):
                    continue                      # this cut would divide the side
                if h_low and o_side != lo_s:
                    inherited = (oblig, FREE)
                elif h_high and o_side != hi_s:
                    inherited = (FREE, oblig)
                else:
                    continue
            for band in ((False, True) if budget > 0 else (False,)):
                rest = budget - band
                tw = self.t_band if band else self.t_cloison
                gap = (self.clear + tw) if band else 0.0
                free = extent - (t[a0] + t[a1]) / 2 - tw - gap
                if free <= 0:
                    continue
                offset = free * share + (t[a0] + tw) / 2
                variants = []
                if band:
                    # A corridor ends at its last door (the architect,
                    # 2026-09-29): each end meets circulation, or a room
                    # across it whose door fits the end (CAP). One end at
                    # least is where it is entered, unless the hub meets it
                    # from the side — then both ends are capped.
                    joins = [bool((flags[e] & BAND and gap >= self.jn - _EPS)
                                  or (flags[e] & HALL and gap >= self.hub_meets - _EPS))
                             for e in (e0, e1)]
                    closable = all(j or not flags[e] & EXT for j, e in zip(joins, (e0, e1)))
                    if closable and any(joins):
                        variants.append((BAND, BAND, inherited))
                    elif (o_side is None and (h_low or h_high)
                          and all(not flags[e] & EXT or flags[e] & STREET for e in (e0, e1))):
                        # the hub meets it from the side; an end on the street
                        # is where the hub stands, and so where it is entered
                        variants.append((BAND, BAND, (lo_s, FREE) if h_low else (FREE, hi_s)))
                    # the ends left open: a room across must take their door
                    lo_at = (x if d is Direction.V else y) + free * share + (t[a0] + tw) / 2
                    opens = tuple((e, lo_at, lo_at + gap, gap)
                                  for j, e in zip(joins, (e0, e1))
                                  if not j and not flags[e] & EXT)
                else:
                    if high_is_hub:
                        variants.append((HALL, 0, inherited))
                    elif low_is_hub:
                        variants.append((0, HALL, inherited))
                    else:
                        variants.append((0, 0, inherited))

                        if o_side is None and h_high:
                            variants.append((HALL, 0, (FREE, 4 + hi_s)))
                        elif o_side is None and h_low:
                            variants.append((0, HALL, (4 + lo_s, FREE)))
                if d is Direction.V:
                    r_low = (x, y, offset, h)
                    r_high = (x + offset + gap, y, w - offset - gap, h)
                else:
                    r_low = (x, y, w, offset)
                    r_high = (x, y + offset + gap, w, h - offset - gap)
                if min(r_low[2], r_low[3], r_high[2], r_high[3]) <= 0:
                    continue
                t_low = list(t); t_low[lo_s] = tw
                t_high = list(t); t_high[hi_s] = tw
                t_low, t_high = tuple(t_low), tuple(t_high)
                for f_lo, f_hi, (ob_low, ob_high) in variants:
                    fl = list(flags); fl[lo_s] = f_lo
                    fh = list(flags); fh[hi_s] = f_hi
                    if self.hub is not None:     # the street matters only to the hub
                        if not h_low:
                            fl = [f & KEEP for f in fl]
                        if not h_high:
                            fh = [f & KEEP for f in fh]
                    fl, fh = tuple(fl), tuple(fh)
                    for b_low in range(max(0, rest - (n_high - 1)), min(rest, n_low - 1) + 1):
                        out.append((d, band,
                                    (low, *r_low, t_low, fl, b_low, ob_low),
                                    (high, *r_high, t_high, fh, rest - b_low, ob_high),
                                    opens if band else ()))
        rng.shuffle(out)
        return out

    def _submasks(self, mask: int, rng: random.Random):
        """Every proper non-empty submask of `mask`, lazily, in random order."""
        bits = []
        m = mask
        while m:
            low = m & -m
            bits.append(low)
            m ^= low
        size = (1 << len(bits)) - 2
        swapped: dict[int, int] = {}
        for k in range(size):                     # lazy Fisher-Yates over 1..size
            j = rng.randrange(k, size)
            pick = swapped.get(j, j)
            swapped[j] = swapped.get(k, k)
            index = pick + 1
            sub = 0
            b = 0
            while index:
                if index & 1:
                    sub |= bits[b]
                index >>= 1
                b += 1
            yield sub

    def _find(self, state, rng: random.Random):
        """(node, ends, pending, caps) for a tree of `state`, or None.

        `ends` are corridor ends left open on the region's sides, (side, lo,
        hi, width); `pending` rooms served only through such an end, (room,
        ((side, lo, hi), ...), module); `caps` rooms along the sides that
        could take a door at an end, (side, lo, hi, module). Where two
        regions meet, every open end must find a room across it whose door
        fits, and every pending room an end within its wall — the corridor
        ENDS at a door (the architect, 2026-09-29).
        """
        mask, x, y, w, h, t, flags, budget, oblig = state
        if mask & (mask - 1) == 0:
            i = mask.bit_length() - 1
            if budget or not self._leaf_fit(i, w, h, t, flags, oblig):
                return None
            span = ((y, y + h), (y, y + h), (x, x + w), (x, x + w))
            caps = () if i == self.hub else tuple(
                (s, *span[s], self.dm_band[i]) for s in range(4) if not flags[s] & EXT)
            if i == self.hub or self._served(i, w, h, flags):
                return self.leaves[i], (), (), caps
            sides = self._pending(i, w, h, flags)
            if not sides:
                return None
            return self.leaves[i], (), ((i, tuple((s, *span[s]) for s in sides),
                                         self.dm_band[i]),), caps
        key = self._key(state)
        if key in self.dead:
            return None
        found = self._alive.get(key)
        if found is not None:
            return found
        self.calls += 1
        if self.calls > self.max_calls:
            raise _OutOfCalls
        if not self._plausible(mask, w, h, t, flags, budget, oblig):
            self.dead.add(key)
            return None
        for low in self._submasks(mask, rng):
            for d, band, s_low, s_high, opens in self._options(state, low, mask ^ low, rng):
                if not (self._check(s_high) and self._check(s_low)):
                    continue
                a = self._find(s_low, rng)
                if a is None:
                    continue
                b = self._find(s_high, rng)
                if b is None:
                    continue
                lo_s, hi_s = (1, 0) if d is Direction.V else (3, 2)
                met = _meet(a, b, lo_s, hi_s, band)
                if met is None:
                    continue
                ends, pending, caps = met
                node = BandCut(d, (a[0], b[0])) if band else Cut(d, False, (a[0], b[0]))
                found = (node, ends + opens, pending, caps)
                self._alive[key] = found
                return found
        self.dead.add(key)
        return None


def _meet(a, b, lo_s: int, hi_s: int, band: bool):
    """Join two siblings' open ends, pending rooms and caps across their cut.

    Across a band nothing meets (its sides are served by it, and an end on
    them would have joined it). Across a plain cut, each open end on the cut
    needs a cap across it — a room covering it whose door fits its width —
    and each pending room loses that side unless an end across falls within
    it; a pending room with no side left is unserved. None if anything fails.
    """
    ends: list = []
    pending: list = []
    for mine, other, side, facing in ((a, b, lo_s, hi_s), (b, a, hi_s, lo_s)):
        for end in mine[1]:
            if end[0] != side:
                ends.append(end)
            elif band or not any(
                c[0] == facing and c[1] <= end[1] + _EPS and c[2] >= end[2] - _EPS
                and c[3] <= end[3] + _EPS for c in other[3]
            ):
                return None
        for room, sides, module in mine[2]:
            here = [sd for sd in sides if sd[0] == side]
            if here and not band and any(
                e[0] == facing and e[1] >= sd[1] - _EPS and e[2] <= sd[2] + _EPS
                and e[3] >= module - _EPS for e in other[1] for sd in here
            ):
                continue
            rest = tuple(sd for sd in sides if sd[0] != side)
            if not rest:
                return None
            pending.append((room, rest, module))
    caps = tuple(c for c in a[3] if c[0] != lo_s) + tuple(c for c in b[3] if c[0] != hi_s)
    return tuple(ends), tuple(pending), caps

def construct(
    brief: Brief,
    rect: tuple[float, float, float, float],
    seed: int,
    tries: int = TRIES,
    max_calls: int = CALLS,
    entry_side: str | None = None,
    open_sides: frozenset[str] | None = None,
) -> list[SlicingTree]:
    """Distinct constructed trees for `brief` on `rect`, most bands first.

    One `Constructor` for the whole call, so what one find proves dead the next
    does not search again; a budget proven empty is skipped outright. The same
    seed always gives the same list.
    """
    finder = Constructor(brief, rect, entry_side, open_sides)
    rng = random.Random(seed)
    bands = len(brief.programme.band_rooms)
    out: list[SlicingTree] = []
    seen: set[SlicingTree] = set()
    for budget in (range(bands, 0, -1) if bands else (0,)):
        for _ in range(tries):
            if finder.proven_empty(budget):
                break
            tree = finder.find(rng, budget, max_calls)
            if tree is None or tree in seen:
                continue
            seen.add(tree)
            out.append(tree)
    return out


def best_start(
    brief: Brief,
    tree0: SlicingTree,
    graph=None,
    seed: int = 0,
    rect: tuple[float, float, float, float] | None = None,
    entry_side: str | None = None,
    tries: int = TRIES,
    max_calls: int = CALLS,
    follow: bool = True,
    open_sides: frozenset[str] | None = None,
) -> SlicingTree:
    """The tree to anneal from: the best that passes every gate among `tree0`
    and the trees `construct` builds on `rect`; `tree0` if none passes.

    The seed competes too, so construction can never cost a plan. Each tree is
    judged by `evaluate`, on a footprint solved for itself (`anneal.refit`);
    ranking by `globale` is the search's own objective, and a tree that fails
    a gate is not ranked at all. `rect` defaults to the brief's envelope;
    `follow=False` judges every tree on it as given (a unit on a floor plate);
    `open_sides` are the sides of `rect` that may take windows (`Constructor`).
    """
    from planfgen.search.anneal import envelope_of, evaluate, grid_for

    grid = grid_for(brief)
    best = evaluate(tree0, brief, grid, graph, 0, follow)
    rect = envelope_of(brief) if rect is None else rect
    for tree in construct(brief, rect, seed, tries, max_calls, entry_side, open_sides):
        if tree == tree0:
            continue
        result = evaluate(tree, brief, grid, graph, 0, follow)
        if result is not None and (best is None or result.cost < best.cost):
            best = result
    return tree0 if best is None else best.tree
