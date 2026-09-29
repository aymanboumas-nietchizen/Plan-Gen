"""Which valid plan should the studio show first? The ranking, measured.

    python tools/probe_ranking.py                        # today's engine, 6 seeds x 3 profiles
    python tools/probe_ranking.py --prefer --every --lean   # the proposed archive feed
    python tools/probe_ranking.py --cases F4 --save f4.pkl  # split long runs, save each
    python tools/probe_ranking.py --load a.pkl,b.pkl --hall-exempt
    python tools/probe_ranking.py --exists              # does a slot-free plan exist at all?

A probe, not engine code. Per case, profile and seed it runs `pipeline.generate`'s
own search — `attempts`, then per attempt `construct.best_start` and `anneal` —
and keeps EVERY candidate that passed every gate (deduplicated; a footprint slid
along the lot is the same plan), not just `best[0]`. The package is imported
read-only; the one patch is a recording wrapper round `anneal._assess`.
`test_ranking.py` checks that the plan `collect` says was returned is the plan
`generate` returns.

Gates are never scored here. Every plan in a pool already passed all of them;
the question is only which of the passing plans comes first.

THE OBJECTIVES (all judgement calls). Adjacences, orientation and circulation as
`metrics.score` computes them, and room proportion, which `compacite` (a MEAN of
min(1, 1/ratio)) measures badly: one 2.4:1 SDB in seven rooms moves `globale` by
about 0.009, less than one orientation preference. Proportion as an architect
signs it is two numbers — `fentes`, the count of non-band rooms over 2:1 net
(`SLOT`), and `pire`, the worst ratio. Plus `ecart`, metres left free against a
party wall: S25 made wall-to-wall the pipeline's first choice, not a gate.

MEASURED 2026-09-30 (PROGRESS.md S30), 6 seeds x 3 profiles x {F3, F4, DEMO,
F3+WC}, 200 iterations, top pick per run with a slot room / wall to wall:

    today (generate's best[0])                         81 %   100 %
    lexi over today's pool                             58 %   100 %
    lexi, pool fed by --prefer --every --lean          42 %   100 %   2.0-3.6 s/run (today 1.6-2.3)
    ... the same, ENTREE not judged (--hall-exempt)    25 %   100 %   (today 57 %)

The slot that remains is F4's cuisine (~2.1 x 5.3): on a wall-to-wall F4 no plan
found is without it; slot-free F4 plans exist ~1.3 m short of the party wall, and
the gallery shows one in every F4 run. With every attempt pooled, 16-38 % of each
case's front is UNSUPPORTED — no positive weighting of the six objectives picks
it — so a slider over a weighted sum cannot reach those plans; with today's
one-attempt pools the front has 1-3 plans and is almost all supported.

THE RULES (see `RANKERS`): `globale` (today), `lexi` (non-dominated plans; wall
to wall first, then fewest slots, then `globale`), `fentes` (slots before wall).
`gallery(pool, k)` is the proposal: the `lexi` head, the fewest-slots plan if
the head has more, then max-min spread over the front, each plan labelled with
what it is best at and what it trades against the head.
"""

from __future__ import annotations

import argparse
import importlib.util
import itertools
import os
import pickle
import random
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from multiprocessing import Pool
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _tool(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


#: A room longer than this on its net dimensions is a slot (S26's threshold).
SLOT = 2.0

#: Room kinds proportion is not judged on. Empty by default: S26 counted the
#: 1.5 x 3.3 m ENTREE as a slot, and so does this. `--hall-exempt` sets it to
#: {"ENTREE"} — a hall is circulation, and an elongated one is ordinary
#: practice — so the report can show both readings.
EXEMPT: frozenset = frozenset()

#: Objective names, all to MAXIMISE (the proportion terms enter negated).
OBJECTIVES = ("adjacences", "orientation", "circulation", "fentes", "pire", "ecart")

#: The smallest difference in each objective that is a difference at all. A
#: plan 0.001 better on circulation is not a trade-off an architect can see, and
#: letting it count fills the front with near-twins and labels one of them
#: "best on circulation". Values are snapped to these steps before dominance:
#: adjacences 0.01 (under the smallest relation, weight 1 in ~30), orientation
#: 0.01 (it moves in steps of 1/n), circulation 0.02 (~0.4 m of run per room
#: or 0.3 points of coefficient), fentes whole rooms, pire 0.1 of ratio,
#: ecart 0.1 m.
RESOLUTION = (0.01, 0.01, 0.02, 1, 0.1, 0.1)


# --- one plan, as the ranking sees it -----------------------------------------

@dataclass(frozen=True)
class Plan:
    """One valid candidate, reduced to what the ranking needs."""

    key: str                     # tree + footprint, for deduplication
    adjacences: float
    orientation: float
    circulation: float
    compacite: float
    globale: float
    rooms: tuple = ()            # (nom, kind, short, long) on net dimensions
    source: str = "anneal"       # "construct" or "anneal"
    #: Metres left free against a party wall: 0 when the building runs wall to
    #: wall, or when the lot has no pair of party walls. Not a gate — S25 made
    #: wall-to-wall the pipeline's first choice, not a rule — so it is an
    #: objective, and the one F4's slot-free plans trade against.
    ecart: float = 0.0

    @property
    def ratios(self) -> list[float]:
        """Net long/short of every room proportion is judged on."""
        return [lg / sh for _, kind, sh, lg in self.rooms if kind not in EXEMPT]

    @property
    def fentes(self) -> int:
        return sum(1 for r in self.ratios if r > SLOT + 1e-9)

    @property
    def pire(self) -> float:
        return max(self.ratios, default=1.0)

    @property
    def slot_rooms(self) -> list[str]:
        return [f"{n} {sh:.2f}x{lg:.2f}" for n, kind, sh, lg in self.rooms
                if kind not in EXEMPT and lg / sh > SLOT + 1e-9]

    def vector(self) -> tuple[float, ...]:
        """The objective vector, every term to maximise."""
        raw = (self.adjacences, self.orientation, self.circulation, -self.fentes, -self.pire,
               -self.ecart)
        return tuple(round(round(v / q) * q, 6) for v, q in zip(raw, RESOLUTION))


def plan_of(result, source: str) -> Plan:
    """A `search.Result` as a `Plan`."""
    brief = result.brief
    kinds = {r.nom: r.kind.name for r in brief.programme.rooms}
    rooms = []
    for cell in result.plan.cells:
        if cell.is_band:
            continue
        w, h = cell.net_dims(brief.profile)
        rooms.append((cell.nom, kinds.get(cell.nom, "?"), round(min(w, h), 3),
                      round(max(w, h), 3)))
    fp = brief.footprint
    where = "" if fp is None else f"@{fp.w:.3f}x{fp.h:.3f}"  # a slid footprint is the same plan
    s = result.scores
    return Plan(repr(result.tree) + where, s.adjacences, s.orientation, s.circulation,
                s.compacite, s.globale, tuple(sorted(rooms)), source, ecart_of(brief))


def ecart_of(brief) -> float:
    """Metres between the footprint and the party-wall span, 0 if none."""
    from planfgen.brief.footprint import party_span
    fp = brief.footprint
    if fp is None:
        return 0.0
    span_w, span_d = party_span(brief.parcel)
    if span_w is not None:
        return round(max(0.0, span_w - fp.w), 3)
    if span_d is not None:
        return round(max(0.0, span_d - fp.h), 3)
    return 0.0


# --- dominance, the front, and what a linear sum can reach --------------------

def dominates(a: tuple, b: tuple) -> bool:
    """a is at least as good as b everywhere and strictly better somewhere."""
    return all(x >= y for x, y in zip(a, b)) and any(x > y for x, y in zip(a, b))


def front(plans: list[Plan]) -> list[Plan]:
    """The non-dominated plans, one per distinct objective vector (the best
    `globale` of each), in descending `globale`."""
    by_vector: dict[tuple, Plan] = {}
    for p in plans:
        v = p.vector()
        if v not in by_vector or p.globale > by_vector[v].globale:
            by_vector[v] = p
    vectors = list(by_vector)
    keep = [v for v in vectors if not any(dominates(u, v) for u in vectors if u != v)]
    return sorted((by_vector[v] for v in keep), key=lambda p: -p.globale)


def simplex(dims: int, step: int) -> list[tuple[float, ...]]:
    """Every weight vector on the simplex with components in multiples of 1/step."""
    out = []
    for parts in itertools.product(range(step + 1), repeat=dims - 1):
        if sum(parts) <= step:
            out.append(tuple(p / step for p in parts) + ((step - sum(parts)) / step,))
    return out


def linear_reach(plans: list[Plan], values, weights) -> set[int]:
    """Indices of `plans` that are the arg-max of SOME weight vector in `weights`
    over the terms `values(plan)` — what a slider over a weighted sum can show.

    Only weight vectors with every component positive are used: a zero weight
    makes every plan tie on that term, and a tie broken by list order is not a
    plan the slider chose. Ties at the top otherwise count as reachable."""
    vals = [values(p) for p in plans]
    reach: set[int] = set()
    for w in weights:
        if min(w) <= 0:
            continue
        sums = [sum(a * b for a, b in zip(w, v)) for v in vals]
        top = max(sums)
        reach.update(i for i, s in enumerate(sums) if s >= top - 1e-9)
    return reach


def metric_terms(p: Plan) -> tuple[float, ...]:
    """The four terms `globale` actually sums, in `metrics.score`'s order."""
    return (p.adjacences, p.orientation, p.circulation, p.compacite)


# --- the rankings -------------------------------------------------------------

def rank_globale(plans: list[Plan]) -> list[Plan]:
    """Today: the weighted sum, best first."""
    return sorted(plans, key=lambda p: (-p.globale, p.key))


#: Below this many metres short of a party wall, a building counts as wall to wall.
WALL_TO_WALL = 0.05


def rank_lexi(plans: list[Plan]) -> list[Plan]:
    """The non-dominated plans: wall to wall first (the pipeline's existing
    order, S25 — the architect's call, not this probe's), then fewest slot
    rooms, then the weighted sum. Proportion is a threshold, not a trade: no
    weight can buy a slot back.

    Over the front, not the pool: `globale` sums the MEAN squareness, the front
    judges the worst room, so the best sum among the fewest-slot plans can be
    dominated — another plan as good on every judgement call with a squarer
    worst room. The head of the list is always on the front."""
    return sorted(front(plans), key=lambda p: (p.ecart > WALL_TO_WALL, p.fentes,
                                               -p.globale, p.key))


def rank_fentes(plans: list[Plan]) -> list[Plan]:
    """As `rank_lexi` with the first two keys swapped: fewest slots even at the
    price of land left free against a party wall. The gallery's second plan."""
    return sorted(front(plans), key=lambda p: (p.fentes, p.ecart > WALL_TO_WALL,
                                               -p.globale, p.key))


RANKERS = {"globale": rank_globale, "lexi": rank_lexi, "fentes": rank_fentes}


def _spread(a: tuple, b: tuple, scale: tuple) -> float:
    return sum(abs(x - y) / s for x, y, s in zip(a, b, scale))


@dataclass
class Pick:
    """A plan in the gallery, and what the UI says about it."""

    plan: Plan
    why: list[str] = field(default_factory=list)      # best-in-archive on ...
    versus: dict[str, float] = field(default_factory=dict)  # delta vs the headline


def gallery(plans: list[Plan], k: int = 4, head=rank_lexi) -> list[Pick]:
    """Up to k plans spanning the non-dominated front.

    The first is `head`'s pick, which must be on the front (`rank_lexi` is). The rest
    are chosen by max-min spread in objective space — each new plan is the one
    farthest from every plan already shown, each objective scaled by its range
    on the front — so the gallery shows plans that differ in kind, not the
    runners-up of one neighbourhood. Deterministic: ties break on `globale`,
    then on the plan's key.
    """
    arch = front(plans)
    if not arch:
        return []
    first = head(plans)[0]
    chosen = [first]
    # The fewest-slots plan is always shown if the head is not one: it is the
    # trade an architect most needs to see, and spread alone may not pick it.
    fewest = rank_fentes(plans)[0]
    if k > 1 and fewest is not first and fewest.fentes < first.fentes:
        chosen.append(fewest)
    vecs = {id(p): p.vector() for p in arch}
    scale = tuple(max(max(c) - min(c), 1e-9) for c in zip(*vecs.values()))
    while len(chosen) < min(k, len(arch)):
        rest = [p for p in arch if p not in chosen]
        best = max(rest, key=lambda p: (
            min(_spread(vecs[id(p)], vecs[id(c)], scale) for c in chosen),
            p.globale, p.key))
        chosen.append(best)
    return [_explain(p, first, arch) for p in chosen]


def _explain(p: Plan, head: Plan, arch: list[Plan]) -> Pick:
    v, h = p.vector(), head.vector()
    cols = list(zip(*(q.vector() for q in arch)))
    why = [name for i, name in enumerate(OBJECTIVES)     # best, where plans differ
           if max(cols[i]) > min(cols[i]) and v[i] >= max(cols[i])]
    versus = {name: round(v[i] - h[i], 3) for i, name in enumerate(OBJECTIVES)
              if v[i] != h[i]}
    return Pick(p, why, versus)


# --- the cases ----------------------------------------------------------------

def case_brief(case: str, profile):
    """(brief, graph) for a studio preset or for F3 with a separate WC."""
    if case == "F3wc":
        pc = _tool("probe_construct")
        rooms, w, h = pc.CASES["F3wc"]
        return pc.brief_for(rooms, w, h, profile), pc.graph_for(rooms)
    return _tool("probe_proportion").brief_for(case, profile)


CASES = ("F3", "F4", "DEMO", "F3wc")

TRIES = 6           # constructions per band budget per attempt (construct.TRIES)
CALLS = 20_000      # Constructor calls per construction (construct.CALLS)


# --- collection (worker side) -------------------------------------------------

_SEEN: list = []


def slot_free_constructor():
    """`search.construct.Constructor` with one more leaf condition: every judged
    room at most `SLOT` on its net dimensions. A generator bias, not a gate —
    whatever it cannot build, the plain `Constructor` still can, and every tree
    it builds still has to pass every real gate."""
    from planfgen.search.construct import Constructor

    class SlotFree(Constructor):
        #: The constructor's rectangles are a local model (it shares a region by
        #: programme area; realise refines the split), so aim a little inside
        #: the threshold: a 2.00:1 in the model realised at 2.01:1.
        MARGIN = 0.95

        def __init__(self, brief, rect, entry_side=None):
            super().__init__(brief, rect, entry_side)
            kinds = {r.nom: r.kind.name for r in brief.programme.rooms}
            self.judged = [kinds[n] not in EXEMPT for n in self.noms]

        def _leaf_ok(self, i, w, h, t, flags, oblig):
            if not super()._leaf_ok(i, w, h, t, flags, oblig):
                return False
            if not self.judged[i]:
                return True
            nw, nh = w - (t[0] + t[1]) / 2, h - (t[2] + t[3]) / 2
            return max(nw, nh) / min(nw, nh) <= SLOT * self.MARGIN
    return SlotFree


def construct_slot_free(brief, rect, seed: int, tries: int = TRIES,
                        calls: int = CALLS) -> list:
    """As `search.construct.construct`, with `slot_free_constructor()`."""
    finder = slot_free_constructor()(brief, rect)
    rng = random.Random(seed)
    bands = len(brief.programme.band_rooms)
    out, seen = [], set()
    for budget in (range(bands, 0, -1) if bands else (0,)):
        for _ in range(tries):
            if finder.proven_empty(budget):
                break
            tree = finder.find(rng, budget, calls)
            if tree is not None and tree not in seen:
                seen.add(tree)
                out.append(tree)
    return out


def fentes_of(result) -> int:
    """Slot rooms of a `search.Result`, as `Plan.fentes` counts them."""
    return plan_of(result, "").fentes


def _install(steer: bool = False) -> None:
    """Record every valid candidate the engine judges. With `steer`, the
    annealer also climbs the lexicographic cost — each slot room costs a whole
    point, more than `globale` can ever give back."""
    import planfgen.search.anneal  # noqa: F401
    mod = sys.modules["planfgen.search.anneal"]
    if steer:
        mod.Result.cost = property(lambda self: fentes_of(self) + 1.0 - self.scores.globale)
    if getattr(mod._assess, "_recording", False):
        return
    original = mod._assess

    def _assess(*args, **kw):
        out = original(*args, **kw)
        if out[0] is not None:
            _SEEN.append(out[0])
        return out
    _assess._recording = True
    mod._assess = _assess


def collect(case: str, profile_name: str, seed: int, iterations: int,
            tries: int = TRIES, calls: int = CALLS, prefer: bool = False,
            every: bool = False, lean: bool = False) -> dict:
    """Every valid plan one `pipeline.generate` judges, and where it came from.

    Exactly `generate`'s search — per attempt `construct.best_start`, then
    `anneal` from it — with every candidate that passes every gate recorded on
    the way (`_install`). Without options, `returned` is what the studio shows.

    With `prefer`, each attempt also builds `construct_slot_free` trees and
    judges them, and the anneal starts from the best plan judged so far by
    `rank_lexi` instead of by `globale`. With `every`, all of
    `pipeline.attempts` feed one pool instead of stopping at the first that
    finds a plan; `returned` stays the first successful attempt's `best[0]`.
    With `lean` as well, attempts after the first successful one are only
    constructed, not annealed — construction is 0.1-0.5 s, an anneal ~1.5 s."""
    from planfgen.brief.regulation import PROFILES
    from planfgen.search import anneal, envelope_of, evaluate, grid_for
    from planfgen.search.construct import best_start
    from planfgen.studio.pipeline import attempts

    _install()
    brief, graph = case_brief(case, PROFILES[profile_name])
    t0 = time.perf_counter()
    plans: dict[str, Plan] = {}
    trees: dict[str, object] = {}
    returned = None
    construct_s = anneal_s = 0.0

    def take(source: str) -> list[Plan]:
        got = []
        for r in _SEEN:
            p = plan_of(r, source)
            plans.setdefault(p.key, p)
            trees.setdefault(p.key, r.tree)
            got.append(plans[p.key])
        _SEEN.clear()
        return got

    for tree0, fitting in attempts(brief):
        b = fitting.brief
        _SEEN.clear()
        ta = time.perf_counter()
        start = best_start(b, tree0, graph, seed, tries=tries, max_calls=calls)
        here = take("construct")
        if prefer:
            for tree in construct_slot_free(b, envelope_of(b), seed, tries, calls):
                evaluate(tree, b, grid_for(b), graph, 0)
            here += take("construct")
            if here:
                start = trees[rank_lexi(here)[0].key]
        construct_s += time.perf_counter() - ta
        ta = time.perf_counter()
        out = [] if lean and returned is not None else anneal(
            b, start, iterations, seed=seed, graph=graph)
        anneal_s += time.perf_counter() - ta
        take("anneal")
        if out and returned is None:
            returned = plan_of(out[0], "anneal").key
        if out and not every:
            break
    return {"case": case, "profile": profile_name, "seed": seed,
            "plans": list(plans.values()), "returned": returned,
            "seconds": time.perf_counter() - t0,
            "construct_s": construct_s, "anneal_s": anneal_s}


def _job(args):
    return collect(*args)


def run_all(cases, seeds: int, iterations: int, tries: int, calls: int,
            steer: bool = False, prefer: bool = False, every: bool = False,
            lean: bool = False) -> list[dict]:
    from planfgen.brief.regulation import PROFILES
    jobs = [(c, p, s, iterations, tries, calls, prefer, every, lean)
            for c in cases for p in PROFILES for s in range(1, seeds + 1)]
    with Pool(os.cpu_count() or 1, initializer=_install, initargs=(steer,)) as pool:
        return pool.map(_job, jobs, chunksize=1)


# --- the report ---------------------------------------------------------------

def _q(xs, fmt="{:.3f}"):
    if not xs:
        return "-"
    xs = sorted(xs)
    med = statistics.median(xs)
    return f"{fmt.format(med)} [{fmt.format(xs[0])}, {fmt.format(xs[-1])}]"


def report(runs: list[dict], k: int = 4) -> None:
    weights4 = simplex(4, 40)            # step 0.025; 9139 of them all-positive
    by_case = defaultdict(list)
    for run in runs:
        by_case[run["case"]].append(run)

    print("\n== POOLS: valid plans per run, and the front over "
          "(adjacences, orientation, circulation, -fentes, -pire, -ecart)")
    for case, rs in by_case.items():
        n = [len(r["plans"]) for r in rs if r["plans"]]
        f = [len(front(r["plans"])) for r in rs if r["plans"]]
        free = [sum(1 for p in r["plans"] if p.fentes == 0) for r in rs if r["plans"]]
        print(f"{case:5} runs with plans {len(n)}/{len(rs)}  plans/run {_q(n, '{:.0f}')}"
              f"  front/run {_q(f, '{:.0f}')}  slot-free plans/run {_q(free, '{:.0f}')}")

    print("\n== REACH: of each run's slot-free front plans, how many is the arg-max of SOME"
          "\n   positive weight vector over metrics' four terms (step 0.025) — i.e. what"
          "\n   a slider over today's sum can ever show")
    for case, rs in by_case.items():
        tot = reach = runs_free = runs_reach = 0
        for r in rs:
            if not r["plans"]:
                continue
            arch = front(r["plans"])
            got = linear_reach(arch, metric_terms, weights4)
            free = [i for i, p in enumerate(arch) if p.fentes == 0]
            tot += len(free)
            reach += sum(1 for i in free if i in got)
            runs_free += bool(free)
            runs_reach += any(i in got for i in free)
        print(f"{case:5} slot-free front plans {tot}, linearly reachable {reach}; "
              f"runs with one {runs_free}, where a slider could show one {runs_reach}")

    weights6 = simplex(len(OBJECTIVES), 20)   # step 0.05; 11628 of them all-positive
    print("\n== CONVEXITY: of each run's front (in its own six objectives), how many"
          "\n   plans are the arg-max of some positive weight vector over those same six")
    for case, rs in by_case.items():
        tot = reach = 0
        for r in rs:
            if r["plans"]:
                arch = front(r["plans"])
                tot += len(arch)
                reach += len(linear_reach(arch, Plan.vector, weights6))
        print(f"{case:5} front plans {tot}, supported (reachable by a weighted sum) {reach}, "
              f"unsupported {tot - reach}")

    print("\n== TOP PICK per run: `today` is what generate returns (the first successful"
          "\n   attempt's best[0]); the others rank the whole pool. Distributions over runs.")
    head = f"{'case':5} {'rule':8} {'slot%':>6} {'wall%':>6} {'fentes':>14} {'pire':>18} " \
           f"{'adjacences':>20} {'orientation':>20} {'circulation':>20} {'globale':>20}"
    print(head)
    lost = defaultdict(list)
    for case, rs in list(by_case.items()) + [("ALL", runs)]:
        tops = {name: [] for name in ("today",) + tuple(RANKERS)}
        for r in rs:
            if not r["plans"]:
                continue
            tops["today"].append(_today(r))
            for name, rank in RANKERS.items():
                tops[name].append(rank(r["plans"])[0])
            if case != "ALL":
                g, x = tops["today"][-1], tops["lexi"][-1]
                lost[case].append(tuple(getattr(x, a) - getattr(g, a) for a in
                                        ("adjacences", "orientation", "circulation", "globale")))
        for name, ps in tops.items():
            if not ps:
                continue
            slot = 100 * sum(1 for p in ps if p.fentes) / len(ps)
            wall = 100 * sum(1 for p in ps if p.ecart <= WALL_TO_WALL) / len(ps)
            print(f"{case:5} {name:8} {slot:5.0f}% {wall:5.0f}% "
                  f"{_q([p.fentes for p in ps], '{:.0f}'):>14} "
                  f"{_q([p.pire for p in ps], '{:.2f}'):>18} "
                  f"{_q([p.adjacences for p in ps]):>20} {_q([p.orientation for p in ps]):>20} "
                  f"{_q([p.circulation for p in ps]):>20} {_q([p.globale for p in ps]):>20}")

    print("\n== COST of lexi vs today on the other terms, per run (after - before)")
    for case, ds in lost.items():
        changed = [d for d in ds if any(abs(x) > 1e-9 for x in d)]
        cols = list(zip(*ds))
        print(f"{case:5} top pick changed in {len(changed)}/{len(ds)} runs;  "
              f"d_adj {_q(list(cols[0]), '{:+.3f}')}  d_orient {_q(list(cols[1]), '{:+.3f}')}"
              f"  d_circ {_q(list(cols[2]), '{:+.3f}')}  d_globale {_q(list(cols[3]), '{:+.3f}')}")

    print("\n== SLOT ROOMS in the top pick, by room (count over runs)")
    for name, rank in [("today", None)] + list(RANKERS.items()):
        rooms = defaultdict(int)
        for r in runs:
            if r["plans"]:
                top = _today(r) if rank is None else rank(r["plans"])[0]
                for s in top.slot_rooms:
                    rooms[s.split()[0]] += 1
        print(f"{name:8} " + ", ".join(f"{n} {c}" for n, c in sorted(rooms.items())))

    print(f"\n== GALLERY (k={k}): size, and how many plans in it are slot-free")
    for case, rs in by_case.items():
        sizes, free, kinds = [], [], defaultdict(int)
        for r in rs:
            if not r["plans"]:
                continue
            g = gallery(r["plans"], k)
            sizes.append(len(g))
            free.append(sum(1 for pk in g if pk.plan.fentes == 0))
            for pk in g[1:]:
                for name in pk.why:
                    kinds[name] += 1
        print(f"{case:5} size {_q(sizes, '{:.0f}')}  slot-free in it {_q(free, '{:.0f}')}"
              f"  alternates best-on: " + ", ".join(f"{n} {c}" for n, c in sorted(kinds.items())))

    print("\n== RUNTIME per run (s): total, construction, anneal; and ranking cost")
    for case, rs in by_case.items():
        t = time.perf_counter()
        for r in rs:
            if r["plans"]:
                gallery(r["plans"], k)
        rank_ms = 1000 * (time.perf_counter() - t) / max(1, len(rs))
        print(f"{case:5} total {_q([r['seconds'] for r in rs], '{:.1f}')}  "
              f"construct {_q([r['construct_s'] for r in rs], '{:.1f}')}  "
              f"anneal {_q([r['anneal_s'] for r in rs], '{:.1f}')}  "
              f"front+gallery {rank_ms:.1f} ms/run")


def _today(run: dict) -> Plan:
    """The plan `generate` returns today, from a pool."""
    same = [p for p in run["plans"] if p.key == run["returned"]]
    return same[0] if same else rank_globale(run["plans"])[0]


def example(runs: list[dict], case: str, profile: str, seed: int, k: int = 4) -> None:
    """One run's gallery, as the UI would receive it."""
    r = next(x for x in runs if (x["case"], x["profile"], x["seed"]) == (case, profile, seed))
    print(f"\n== EXAMPLE {case} {profile} seed {seed}: {len(r['plans'])} valid, "
          f"front {len(front(r['plans']))}")
    top = rank_globale(r["plans"])[0]
    print(f"globale pick: g={top.globale:.3f} fentes={top.fentes} {top.slot_rooms}")
    for i, pk in enumerate(gallery(r["plans"], k)):
        p = pk.plan
        print(f"  [{i}] g={p.globale:.3f} adj={p.adjacences:.3f} or={p.orientation:.2f} "
              f"circ={p.circulation:.3f} fentes={p.fentes} pire={p.pire:.2f} ecart={p.ecart:.2f} "
              f"best-on={pk.why} vs-head={pk.versus} {p.slot_rooms}")


def slot_free_exists(case: str, profile_name: str, tries: int = 6,
                     calls: int = 200_000) -> list[tuple[str, int, int]]:
    """Does a slot-free valid plan exist at all, on each envelope `generate` tries?

    `construct_slot_free`, then the real gates. Per attempt: (footprint, trees
    built, trees whose REALISED plan passes every gate with no slot room). A
    search, so "not found" is evidence, not proof."""
    from planfgen.brief.regulation import PROFILES
    from planfgen.search import envelope_of, evaluate, grid_for
    from planfgen.studio.pipeline import attempts

    brief, graph = case_brief(case, PROFILES[profile_name])
    out = []
    for _, fitting in attempts(brief):
        b = fitting.brief
        built = construct_slot_free(b, envelope_of(b), 0, tries, calls)
        ok = 0
        for tree in built:
            r = evaluate(tree, b, grid_for(b), graph, 0)
            ok += r is not None and plan_of(r, "").fentes == 0
        fp = fitting.footprint
        out.append((f"{fp.w:.2f}x{fp.h:.2f}", len(built), ok))
    return out


def _exists_job(args):
    return args, slot_free_exists(*args)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=6)
    parser.add_argument("--iters", type=int, default=200)
    parser.add_argument("--cases", default=",".join(CASES))
    parser.add_argument("--tries", type=int, default=TRIES)
    parser.add_argument("--calls", type=int, default=CALLS)
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--steer", action="store_true",
                        help="the annealer climbs the lexicographic cost too")
    parser.add_argument("--hall-exempt", action="store_true",
                        help="do not judge the ENTREE's proportion")
    parser.add_argument("--prefer", action="store_true",
                        help="construct slot-free trees first (see `collect`)")
    parser.add_argument("--every", action="store_true",
                        help="pool every attempt, not just the first that finds a plan")
    parser.add_argument("--lean", action="store_true",
                        help="with --every: anneal only the first successful attempt")
    parser.add_argument("--exists", action="store_true",
                        help="does a slot-free valid plan exist at all, per case and profile")
    parser.add_argument("--save")
    parser.add_argument("--load")
    args = parser.parse_args()
    if args.hall_exempt:
        global EXEMPT
        EXEMPT = frozenset({"ENTREE"})
    if args.exists:
        from planfgen.brief.regulation import PROFILES
        jobs = [(c, p) for c in args.cases.split(",") for p in PROFILES]
        with Pool(os.cpu_count() or 1) as pool:
            for (c, p), rows in pool.imap(_exists_job, jobs):
                print(f"{c:5} {p:11} " + " | ".join(
                    f"att{i} {fp}: {n} slot-free trees, {ok} valid"
                    for i, (fp, n, ok) in enumerate(rows)), flush=True)
        return
    if args.load:
        runs = []
        for path in args.load.split(","):
            with open(path, "rb") as fh:
                runs += pickle.load(fh)
    else:
        runs = run_all(args.cases.split(","), args.seeds, args.iters, args.tries, args.calls,
                       args.steer, args.prefer, args.every, args.lean)
        if args.save:
            with open(args.save, "wb") as fh:
                pickle.dump(runs, fh)
    report(runs, args.k)
    for case in args.cases.split(","):
        if any(r["case"] == case and r["plans"] for r in runs):
            r = next(r for r in runs if r["case"] == case and r["plans"])
            example(runs, case, r["profile"], r["seed"], args.k)


if __name__ == "__main__":
    main()
