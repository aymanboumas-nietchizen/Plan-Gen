"""Can the engine BUILD nested plans? A constructive seed, measured against the walk.

    python tools/probe_construct.py                     # every variant, 6 seeds, 200 its
    python tools/probe_construct.py base construct      # named variants only
    python tools/probe_construct.py --seeds 4 --iters 200 --cases F3wc,F3preset

A probe, not engine code: every variant below is a monkeypatch installed in the
worker processes, so the package is exactly what is committed. The one piece of
real logic, `Finder`, is the prototype `planfgen-engine` is asked to build into
`search/` (PROGRESS.md S27 carries the spec).

WHY THE WALK CANNOT GET THERE (2026-09-28, S27)

1. The search's envelope is frozen to its SEED. `pipeline.fit` solves the
   footprint for the seed tree; the annealer realises every candidate on it; and
   between party walls `shape_footprint` is a no-op. A band's area is an output,
   so a tree with more (or longer) corridor than the seed steals it from the rooms:
   every 2-band tree on the F3/F4 seed footprints misses its areas by 4.5-9 %, and
   the area gate is 5 %. `insert_band` can propose a degagement; nothing can
   accept one.
2. Valid plans are sparse and isolated. Around a hand-built F3 one furniture
   miss from passing (Entree 1.33 m wide, needs 1.40), 0 of 341 one-move and 3 of
   34 505 two-move neighbours pass every gate. Exact areas leave no continuous
   knob, so a guided walk has nothing to slide down.
3. A T-junction between two bands is a door as far as reachability knows. The
   band's end is `corridor_clear + cloison_t` wide: 0.90 m on the decret, under
   the 1.00 m door module, so on `economique` a degagement can never connect.

WHAT BUILDS THEM: `Finder`. Realise is top-down and a subtree's rectangle depends
only on WHICH rooms are below it, so buildability decomposes. A region is (rooms,
net extent, wall kinds, what runs along each side, band budget, what the hub owes
an ancestor); it is buildable iff it is one room that furnishes and touches
circulation over a door's width, or a cut or band splits it into two buildable
regions. A randomised depth-first search over that recursion, remembering dead
regions, returns trees in which every room furnishes and is served — the plans
the walk cannot reach — and the real gates then judge them.

Measured 2026-09-28, 6 seeds x 3 profiles, 200 iterations, through
`pipeline.generate` (plans found / 18; construction at 6 tries x 100k calls):

    case       base  refit+junct  construct  +refit  +junct  +refit+junct
    F3wc         2        1          18        18      18        18
    F3wc+deg     0        0          18        18      18        18
    F4wc         0        0           6         6       6         6
    F4wc+deg     0        0           8        11       8        14
    F2           1        -           1         1       1         1
    F3preset    15        -          18        18      18        18
    F4preset    12        -          18        18      18        18

Construction is the lever; refit and the open junction only matter once a plan
needs two bands (F4wc+deg 8 -> 14; the junction alone buys the decret's 3).
`tools/probe_programmes.py`, studio column: 25/72 -> 46/72 (F3 with its WC
0 -> 12/12, F4 0 -> 8/12, the -WC-Entree rows unchanged or better). COST: a
generate that finds nothing now takes 45-90 s instead of ~1 s (2 tries x 30k
calls: 2-13 s, but F4wc 6 -> 0 and F4wc+deg 14 -> 6). Speed is part of the spec.

PROPORTION IS NOT FIXED BY THIS. `probe_proportion.py`: the SDB slot is gone,
the Entree (~1.5 x 3.3) and the F4 Cuisine (~2.0 x 5.4, now in all 12 plans)
remain, DEMO goes from 5 slots to 11. Among 31 valid constructed F4 plans on the
decret every one has the 2.8:1 cuisine; on F3 slot-free plans exist and
`globale` ranks them third. That half is the objective's, not the search's.

F2 is geometric, not a search failure: on the wall-to-wall envelopes of both
sourced profiles no slicing tree with at most one band furnishes all four rooms
at their exact areas (`--f2`, a necessary condition only).
"""

from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import replace
from multiprocessing import Pool

from shapely.geometry import Polygon

from planfgen.brief import (
    Brief, EdgeSpec, EdgeType, Orientation, Parcel, Programme, RoomSpec, RoomType,
    check_feasibility,
)
from planfgen.brief.footprint import fit_footprint, party_span, place_footprint
from planfgen.brief.plan import InfeasibleBrief
from planfgen.brief.regulation import PROFILES
from planfgen.fabric.axis import WallKind
from planfgen.habitability.check import fits
from planfgen.habitability.furniture import FURNITURE
from planfgen.partition import BandCut, Cut, Direction, Leaf, SlicingTree
from planfgen.partition.plan import SpaceCell
from planfgen.partition.tree import BAND_WALL
from planfgen.studio.presets import PRESETS
from planfgen.topology import ProgrammeGraph, Relation, RelationType

# `planfgen.search` re-exports the function `anneal`, which shadows the module.
import planfgen.search.anneal  # noqa: E402,F401
ANNEAL = sys.modules["planfgen.search.anneal"]

# --- the constructive search ----------------------------------------------

SIDES = ("left", "right", "bottom", "top")
BAND, STREET, HALL = 1, 2, 4          # what runs along a region's side
CIRC = BAND | HALL
NO_OBLIGATION = -1                    # else 0-3: hub must TOUCH side; 4-7: SPAN it


class Finder:
    """Randomised depth-first construction of trees whose rooms furnish and are served.

    The hub is the room the front door opens into and which may be walked
    through: the ENTREE, or failing one the SEJOUR. A band whose ends meet no
    circulation is *floating* and the hub, somewhere below it, must meet it; a
    cut may declare one side of a sibling to be the hub, and the hub then owes
    that sibling the whole side. Both are carried down as `oblig`.

    Everything this local model does not see — dead-end runs, the wall graph,
    a hub that fails to have frontage in the fabric's sense — is left to the
    real gates, which every returned tree must still pass.
    """

    #: Metres to which a dead region's extent is rounded when remembered.
    Q = 0.02
    #: Relative slack on the cheap necessary conditions, so they never prune a
    #: buildable region. The leaf test is the exact furniture gate.
    SLACK = 0.03

    def __init__(self, brief: Brief, rect, max_bands: int, junction_open: bool = True):
        self.prof = brief.profile
        programme = brief.programme
        self.rect = rect
        self.max_bands = max_bands
        self.area = {r.nom: r.surface_utile for r in programme.rooms if not r.kind.names_band}
        self.kind = {r.nom: r.kind for r in programme.rooms}
        self.hub = next((n for n in self.area if self.kind[n] is RoomType.ENTREE), None)
        if self.hub is None:
            self.hub = next((n for n in self.area if self.kind[n] is RoomType.SEJOUR), None)
        self.street = SIDES.index(brief.parcel.side_of(brief.parcel.entry_edge))
        self.dm = self.prof.door_module
        self.jn = min(self.dm, self.prof.corridor_clear) if junction_open else self.dm
        self.th = {k: self.prof.thickness_of(k.value) for k in WallKind}
        self.rooms = tuple(sorted(self.area))
        self.dead: set = set()
        self.calls = 0
        self.max_calls = 0

    def find(self, rng: random.Random, budget: int, max_calls: int = 100_000):
        """One tree with exactly `budget` bands, or None (none, or out of calls)."""
        self.calls, self.max_calls = 0, max_calls
        kinds = (WallKind.FACADE,) * 4
        flags = tuple(STREET if i == self.street else 0 for i in range(4))
        try:
            node = self._find((self.rooms, self.rect, kinds, flags, budget, NO_OBLIGATION), rng)
        except TimeoutError:
            return None
        return None if node is None else SlicingTree(node)

    # --- the local model ---------------------------------------------------
    def _net(self, rect, kinds):
        t = [self.th[k] for k in kinds]
        return rect[2] - (t[0] + t[1]) / 2, rect[3] - (t[2] + t[3]) / 2

    def _leaf_ok(self, nom, rect, kinds, flags, oblig) -> bool:
        x, y, w, h = rect
        cell = SpaceCell(nom, x, y, w, h, dict(zip(SIDES, kinds)))
        spec = FURNITURE.get(self.kind[nom])
        if spec is not None and not fits(cell, spec, self.prof):
            return False
        minimum = self.prof.min_area.get(self.kind[nom])
        if minimum:
            a, b = cell.net_dims(self.prof)
            if a * b < minimum:
                return False
        side = lambda i: h if i < 2 else w  # noqa: E731
        if nom == self.hub:
            if not flags[self.street] & STREET:
                return False
            return oblig == NO_OBLIGATION or oblig >= 4 or side(oblig) >= self.jn - 1e-9
        return any(f & CIRC and side(i) >= self.dm - 1e-9 for i, f in enumerate(flags))

    def _furnishable(self, nom, depth=None, nw=None, nh=None) -> bool:
        spec = FURNITURE.get(self.kind[nom])
        if not spec:
            return True
        k, a = self.SLACK, self.area[nom]

        def ok(p):
            q = a / p
            s, long = min(p, q), max(p, q)
            return (s >= spec.min_side * (1 - k) and long >= spec.min_long * (1 - k)
                    and (spec.max_ratio is None or long / s <= spec.max_ratio * (1 + k)))
        if depth is not None:
            return ok(depth)
        lo, hi = a / nh * (1 - k), nw * (1 + k)
        probes = (lo, hi, a ** 0.5, spec.min_side, spec.min_long,
                  a / spec.min_side, a / spec.min_long)
        return any(lo <= p <= hi and ok(p) for p in probes if p > 0)

    def _plausible(self, rooms, rect, kinds, flags, budget, oblig) -> bool:
        nw, nh = self._net(rect, kinds)
        if nw <= 0 or nh <= 0:
            return False
        if not all(self._furnishable(r, nw=nw, nh=nh) for r in rooms):
            return False
        if self.hub not in rooms:
            if oblig != NO_OBLIGATION:
                return False
            served = [i for i, f in enumerate(flags) if f & CIRC]
            if not served:
                return False
            if budget == 0 and len(served) == 1:
                depth = nw if served[0] < 2 else nh      # every room a slab across
                if not all(self._furnishable(r, depth=depth) for r in rooms):
                    return False
        return True

    def _splits(self, rooms, rect, kinds, flags, budget, oblig):
        x, y, w, h = rect
        t = [self.th[k] for k in kinds]
        hub = self.hub
        o_side = oblig % 4 if oblig != NO_OBLIGATION else None
        o_span = oblig >= 4
        n = len(rooms)
        for mask in range(1, (1 << n) - 1):
            low = tuple(r for i, r in enumerate(rooms) if mask >> i & 1)
            high = tuple(r for i, r in enumerate(rooms) if not mask >> i & 1)
            d_low = sum(self.area[r] for r in low)
            share = d_low / (d_low + sum(self.area[r] for r in high))
            h_low, h_high = hub in low, hub in high
            for d in (Direction.V, Direction.H):
                if d is Direction.V:
                    lo_s, hi_s, a0, a1, e0, e1, extent = 1, 0, 0, 1, 2, 3, w
                else:
                    lo_s, hi_s, a0, a1, e0, e1, extent = 3, 2, 2, 3, 0, 1, h
                inherited = (NO_OBLIGATION, NO_OBLIGATION)
                if o_side is not None:
                    if o_span and o_side in (e0, e1):
                        continue                  # this cut would divide the side
                    if h_low and o_side != lo_s:
                        inherited = (oblig, NO_OBLIGATION)
                    elif h_high and o_side != hi_s:
                        inherited = (NO_OBLIGATION, oblig)
                    else:
                        continue
                for band in ((False, True) if budget > 0 else (False,)):
                    rest = budget - band
                    tw = self.th[BAND_WALL] if band else self.th[WallKind.CLOISON]
                    gap = (self.prof.corridor_clear + tw) if band else 0.0
                    free = extent - (t[a0] + t[a1]) / 2 - tw - gap
                    if free <= 0:
                        continue
                    offset = free * share + (t[a0] + tw) / 2
                    wall = BAND_WALL if band else WallKind.CLOISON
                    variants = []
                    if band:
                        ends = flags[e0] | flags[e1]
                        if ends & CIRC and gap >= self.jn - 1e-9:
                            variants.append((BAND, BAND, inherited))
                        elif o_side is None and (h_low or h_high):
                            variants.append((BAND, BAND, (lo_s, NO_OBLIGATION) if h_low
                                             else (NO_OBLIGATION, hi_s)))
                    else:
                        variants.append((0, 0, inherited))
                        if high == (hub,):
                            variants[0] = (HALL, 0, inherited)
                        elif low == (hub,):
                            variants[0] = (0, HALL, inherited)
                        elif o_side is None and h_high:
                            variants.append((HALL, 0, (NO_OBLIGATION, 4 + hi_s)))
                        elif o_side is None and h_low:
                            variants.append((0, HALL, (4 + lo_s, NO_OBLIGATION)))
                    if d is Direction.V:
                        r_low = (x, y, offset, h)
                        r_high = (x + offset + gap, y, w - offset - gap, h)
                    else:
                        r_low = (x, y, w, offset)
                        r_high = (x, y + offset + gap, w, h - offset - gap)
                    if min(r_low[2], r_low[3], r_high[2], r_high[3]) <= 0:
                        continue
                    k_low = list(kinds); k_low[lo_s] = wall
                    k_high = list(kinds); k_high[hi_s] = wall
                    for f_lo, f_hi, (ob_low, ob_high) in variants:
                        fl = list(flags); fl[lo_s] = f_lo
                        fh = list(flags); fh[hi_s] = f_hi
                        if hub is not None:     # the street matters only to the hub
                            if not h_low: fl = [f & CIRC for f in fl]
                            if not h_high: fh = [f & CIRC for f in fh]
                        for b_low in range(rest + 1):
                            yield (d, band,
                                   (low, r_low, tuple(k_low), tuple(fl), b_low, ob_low),
                                   (high, r_high, tuple(k_high), tuple(fh), rest - b_low, ob_high))

    def _find(self, state, rng):
        rooms, rect, kinds, flags, budget, oblig = state
        key = (rooms, round(rect[2] / self.Q), round(rect[3] / self.Q),
               kinds, flags, budget, oblig)
        if key in self.dead:
            return None
        self.calls += 1
        if self.calls > self.max_calls:
            raise TimeoutError
        if len(rooms) == 1:
            if budget == 0 and self._leaf_ok(rooms[0], rect, kinds, flags, oblig):
                return Leaf(rooms[0])
            self.dead.add(key)
            return None
        if not self._plausible(*state):
            self.dead.add(key)
            return None
        splits = list(self._splits(*state))
        rng.shuffle(splits)
        for d, band, low, high in splits:
            a = self._find(low, rng)
            if a is None:
                continue
            b = self._find(high, rng)
            if b is None:
                continue
            return BandCut(d, (a, b)) if band else Cut(d, False, (a, b))
        self.dead.add(key)
        return None


# --- the variants, as patches ------------------------------------------------

def refit(tree: SlicingTree, brief: Brief, _cache: dict = {}) -> Brief:  # noqa: B006
    """The envelope follows the tree: re-solve the free dimension for THIS tree,
    keeping the party span or the current proportion."""
    fp = brief.footprint
    if fp is None:
        return brief
    span_w, span_d = party_span(brief.parcel)
    spans = (span_w is not None and abs(fp.w - span_w) < 1e-6) or (
        span_d is not None and abs(fp.h - span_d) < 1e-6)
    aspect = None if spans else round(fp.aspect, 9)
    key = (tree, aspect, id(brief.programme), id(brief.parcel), id(brief.profile))
    if key not in _cache:
        try:
            solved = fit_footprint(brief.programme, brief.parcel, brief.profile, tree, aspect)
            placed = place_footprint(solved, brief.parcel)
            _cache[key] = placed if placed.buildable(brief.parcel) else solved
        except (ValueError, InfeasibleBrief):
            _cache[key] = None
    new = _cache[key]
    return brief if new is None else replace(brief, footprint=new)


def patch_refit() -> None:
    original = ANNEAL._assess

    def _assess(tree, brief, grid, graph, iteration, measure):
        fitted = refit(tree, brief)
        return original(tree, fitted, ANNEAL.grid_for(fitted), graph, iteration, measure)
    ANNEAL._assess = _assess


def patch_junction() -> None:
    """Two circulation spaces meeting open onto each other over the corridor's
    clear width: an opening with no leaf, so the door module does not apply."""
    import planfgen.circulation.shape as shape
    import planfgen.fabric.plan as fabric_plan
    tol = 1e-9

    def door_capable(self, a, b):
        run = self.shared_wall_length(a, b)
        if self.spaces[a].kind.is_circulation and self.spaces[b].kind.is_circulation:
            return run + tol >= min(self.profile.door_module, self.profile.corridor_clear)
        return run >= self.profile.door_module

    def _served_interval(fabric, space, axis, door_module):
        low = high = None
        for nom, other in fabric.spaces.items():
            if other is space or not fabric.door_capable(space.nom, nom):
                continue
            start = max(space.net_polygon.bounds[axis], other.net_polygon.bounds[axis])
            stop = min(space.net_polygon.bounds[axis + 2], other.net_polygon.bounds[axis + 2])
            if stop - start <= tol:
                if abs(stop - start) <= 0.2 + tol:       # end-on: served where they meet
                    start = stop = (start + stop) / 2
                else:
                    continue
            low = start if low is None else min(low, start)
            high = stop if high is None else max(high, stop)
        return None if low is None else (low, high)

    fabric_plan.FabricPlan.door_capable = door_capable
    shape._served_interval = _served_interval


TRIES = 6
CALLS = 100_000


def patch_construct() -> None:
    """Before each anneal, construct trees and anneal from the best-scoring tree
    that passes every gate — the attempt's own seed included, and it if none does."""
    import planfgen.studio.pipeline as pipeline
    original = pipeline.anneal

    def anneal(brief, tree0, n_iter, seed=0, graph=None, stats=None, **kw):
        bands = len(brief.programme.band_rooms)
        finder = Finder(brief, ANNEAL.envelope_of(brief), bands)
        rng = random.Random(seed)
        # the attempt's own seed competes too: construction must never cost a plan
        best = ANNEAL.evaluate(tree0, brief, ANNEAL.grid_for(brief), graph, 0)
        seen = {tree0}
        for budget in (range(bands, 0, -1) if bands else (0,)):
            for _ in range(TRIES):
                tree = finder.find(rng, budget, CALLS)
                if tree is None or tree in seen:
                    continue
                seen.add(tree)
                result = ANNEAL.evaluate(tree, brief, ANNEAL.grid_for(brief), graph, 0)
                if result is not None and (best is None or result.cost < best.cost):
                    best = result
        start = best.tree if best is not None else tree0
        return original(brief, start, n_iter, seed=seed, graph=graph, stats=stats, **kw)
    pipeline.anneal = anneal


VARIANTS = {
    "base": (),
    "refit+junction": (patch_refit, patch_junction),
    "construct": (patch_construct,),
    "construct+refit+junction": (patch_refit, patch_junction, patch_construct),
}

# --- the cases ----------------------------------------------------------------

EDGES = ("STREET", "MITOYEN", "COURT", "MITOYEN")
_F3WC = [("Entree", "ENTREE", 5, ""), ("Sejour", "SEJOUR", 24, "S"),
         ("Cuisine", "CUISINE", 9, "N"), ("Ch1", "CHAMBRE_PRINCIPALE", 13, "S"),
         ("Ch2", "CHAMBRE", 11, "E"), ("SDB", "SDB", 5, ""), ("WC", "WC", 2, ""),
         ("Couloir", "COULOIR", 6, "")]
_F4WC = [("Entree", "ENTREE", 5, ""), ("Sejour", "SEJOUR", 30, "S"),
         ("Cuisine", "CUISINE", 11, "N"), ("Ch1", "CHAMBRE_PRINCIPALE", 14, "S"),
         ("Ch2", "CHAMBRE", 12, "E"), ("Ch3", "CHAMBRE", 11, "O"),
         ("SDB", "SDB", 5, ""), ("WC", "WC", 2, ""), ("Couloir", "COULOIR", 9, "")]
_DEG = [("Degagement", "COULOIR", 3, "")]
_F2 = [("Sejour", "SEJOUR", 18, "S"), ("Cuisine", "CUISINE", 7, "N"),
       ("Ch1", "CHAMBRE_PRINCIPALE", 12, "S"), ("SDB", "SDB", 4, ""),
       ("Couloir", "COULOIR", 5, "")]

#: name -> (rooms, lot width, lot depth). A second COULOIR names a second band.
CASES = {
    "F3wc": (_F3WC, 9, 11), "F3wc+deg": (_F3WC + _DEG, 9, 11),
    "F4wc": (_F4WC, 11, 13), "F4wc+deg": (_F4WC + _DEG, 11, 13),
    "F2": (_F2, 8, 8),
    "F3preset": (list(PRESETS["F3"].rooms), 9, 11),
    "F4preset": (list(PRESETS["F4"].rooms), 11, 13),
}


def graph_for(rooms) -> ProgrammeGraph:
    noms = {n: k for n, k, _, _ in rooms}
    rel = [Relation("Couloir", n, RelationType.CONNECTED, 2.0) for n, k in noms.items()
           if k in ("CHAMBRE", "CHAMBRE_PRINCIPALE", "SDB", "WC")]
    if "Entree" in noms:
        rel += [Relation("Entree", "Sejour", RelationType.CONNECTED, 2.0),
                Relation("Entree", "Couloir", RelationType.CONNECTED, 2.0)]
    else:
        rel.append(Relation("Couloir", "Sejour", RelationType.CONNECTED, 2.0))
    rel += [Relation("Sejour", "Cuisine", RelationType.CONNECTED, 1.5),
            Relation("Cuisine", "SDB", RelationType.ADJACENT, 1.0),
            Relation("SDB", "Sejour", RelationType.SEPARATED, 1.0)]
    return ProgrammeGraph(rel)


def brief_for(rooms, width: float, depth: float, profile) -> Brief:
    programme = Programme([
        RoomSpec(nom=n, kind=RoomType[k], surface_utile=float(a), couleur="#888888",
                 orientation_pref=Orientation[o] if o else None)
        for n, k, a, o in rooms
    ])
    parcel = Parcel(
        outline=Polygon([(0, 0), (width, 0), (width, depth), (0, depth)]),
        edges=[EdgeSpec(i, EdgeType[e]) for i, e in enumerate(EDGES)],
        north=0.0, entry_edge=0,
    )
    return Brief(programme, parcel, profile, check_feasibility(programme, parcel, profile))


# --- the run ------------------------------------------------------------------

def _install(variant: str, tries: int = TRIES, calls: int = CALLS) -> None:
    global TRIES, CALLS
    TRIES, CALLS = tries, calls
    for patch in VARIANTS[variant]:
        patch()


def _job(args):
    case, profile_name, seed, iterations = args
    from planfgen.studio.pipeline import generate
    rooms, w, h = CASES[case]
    brief = brief_for(rooms, w, h, PROFILES[profile_name])
    t0 = time.perf_counter()
    run = generate(brief, graph_for(rooms), seed, iterations)
    if not run.ok:
        return case, profile_name, None, None, time.perf_counter() - t0
    ratios = []
    for cell in run.result.plan.cells:
        if not cell.is_band:
            a, b = cell.net_dims(run.result.brief.profile)
            ratios.append(max(a, b) / min(a, b))
    return case, profile_name, run.result.scores.globale, ratios, time.perf_counter() - t0


def measure(variant: str, cases, seeds: int, iterations: int,
            tries: int = TRIES, calls: int = CALLS) -> None:
    jobs = [(c, p, s, iterations) for c in cases for p in PROFILES for s in range(1, seeds + 1)]
    with Pool(os.cpu_count() or 1, initializer=_install,
              initargs=(variant, tries, calls)) as pool:
        results = pool.map(_job, jobs, chunksize=1)
    by = defaultdict(list)
    seconds = defaultdict(list)
    for case, profile_name, globale, ratios, took in results:
        by[case].append((profile_name, globale, ratios))
        seconds[case].append(took)
    for case in cases:
        rows = by[case]
        per = "  ".join(
            f"{p[:5]} {sum(1 for q, g, _ in rows if q == p and g is not None)}/{seeds}"
            for p in PROFILES)
        ok = [(g, r) for _, g, r in rows if g is not None]
        tail = ""
        if ok:
            scores = sorted(g for g, _ in ok)
            slots = sum(1 for _, r in ok for x in r if x > 2.0)
            tail = (f"  globale med {statistics.median(scores):.3f} "
                    f"[{scores[0]:.3f}, {scores[-1]:.3f}]  slots>2:1 {slots}")
        took = sorted(seconds[case])
        print(f"{variant:26} {case:9} {per}  total {len(ok)}/{len(rows)}{tail}"
              f"  s/run med {statistics.median(took):.1f} max {took[-1]:.1f}", flush=True)


def f2_furnishable() -> None:
    """Necessary condition only: does ANY tree with at most one band furnish every
    F2 room at its exact area, on each envelope the studio would try?"""
    from planfgen.studio.pipeline import attempts

    class FurnitureOnly(Finder):
        def _leaf_ok(self, nom, rect, kinds, flags, oblig):
            x, y, w, h = rect
            spec = FURNITURE.get(self.kind[nom])
            cell = SpaceCell(nom, x, y, w, h, dict(zip(SIDES, kinds)))
            return spec is None or fits(cell, spec, self.prof)

        def _plausible(self, rooms, rect, kinds, flags, budget, oblig):
            nw, nh = self._net(rect, kinds)
            return nw > 0 and nh > 0 and all(
                self._furnishable(r, nw=nw, nh=nh) for r in rooms)

        def _splits(self, rooms, rect, kinds, flags, budget, oblig):
            yield from super()._splits(rooms, rect, kinds, (BAND,) * 4, budget, NO_OBLIGATION)

    rooms, w, h = CASES["F2"]
    for name, profile in PROFILES.items():
        brief = brief_for(rooms, w, h, profile)
        for i, (_, fitting) in enumerate(attempts(brief)):
            finder = FurnitureOnly(fitting.brief, ANNEAL.envelope_of(fitting.brief), 1)
            finder.hub = None
            found = finder.find(random.Random(0), 1, 5_000_000) is not None
            print(f"F2 {name:11} attempt {i} {fitting.footprint.w:.2f} x "
                  f"{fitting.footprint.h:.2f}: a furnishable 1-band tree "
                  f"{'exists' if found else 'does NOT exist'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("variants", nargs="*", default=list(VARIANTS))
    parser.add_argument("--seeds", type=int, default=6)
    parser.add_argument("--iters", type=int, default=200)
    parser.add_argument("--cases", default=",".join(CASES))
    parser.add_argument("--tries", type=int, default=TRIES)
    parser.add_argument("--calls", type=int, default=CALLS)
    parser.add_argument("--f2", action="store_true")
    args = parser.parse_args()
    if args.f2:
        f2_furnishable()
        return
    for variant in args.variants:
        measure(variant, args.cases.split(","), args.seeds, args.iters,
                args.tries, args.calls)


if __name__ == "__main__":
    main()
