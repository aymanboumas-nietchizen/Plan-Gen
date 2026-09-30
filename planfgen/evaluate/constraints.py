"""Gates — a candidate either passes or is discarded.

CLAUDE.md: area, coverage, orthogonality, reachability and furniture fit are
never traded off in a score. A plan with a 7 m2 chambre is not a slightly worse
plan, it is not a plan. Only judgement calls get scored, and those live in
`metrics.py`.

**Aspect ratio and minimum width are NOT on that list, and are not gated here.**
Both were once, and it was wrong twice over. CLAUDE.md names compactness among
the *scored* judgement calls, and v1 held `MaxRatioRule` and every `MinWidthRule`
as soft warnings — only the minimum *areas* and the corridor width were hard.
ARCHITECTURE section 6 shows `if not part.aspects_ok(): return None` in its
sketch of the loop, but that passage is arguing about cost, not about which
checks are gates, and the rules file governs where the two disagree.

It mattered: gating aspect discarded 222 of 500 candidates on the v1 brief and
hid the real reason that brief cannot be built, which is that the furniture does
not fit — the very failure ARCHITECTURE section 1 describes. Shape is now
protected by `FURNITURE_GATE`, which is a gate CLAUDE.md does authorise and
which asks the question that actually matters: not "is this room a slot" but
"does a bed go in it".

**Daylight is a gate** since 2026-09-29 (the architect's decision): decret
2-64-445 ART. 7 lights every habitable room and the kitchen to `daylight_ratio`
of its floor and never under 1 m2, and a bay under 0.35 m is not a window. A
bedroom without a window is not a darker plan, it is not a legal one.
`DAYLIGHT_GATE` asks it of the partition cells with float arithmetic, measuring
frontage exactly as the fabric will (`fabric.plan.edge_slack`), and sizes the
windows with the same functions L6 uses (`openings.window`), so the gate and the
drawn windows agree.

The gates run cheapest first and the first failure wins, so a candidate that
fails on a float comparison never pays for the wall graph. Building the fabric
is by far the most expensive thing here, and only `REACHABLE_GATE` needs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from planfgen.brief.footprint import Footprint
from planfgen.brief.plan import Brief
from planfgen.circulation.reachable import reachable
from planfgen.circulation.shape import circulation_runs
from planfgen.fabric.axis import TOL, WallKind
from planfgen.fabric.plan import edge_slack
from planfgen.habitability.check import fit_report, furniture_shortfall
from planfgen.openings.window import DAYLIGHT_KINDS, width_owed, window_capacity

#: How far a room's net area may miss its target and still be a plan, as a
#: fraction. Free cuts are exact, so this slack exists for structural ones,
#: where the grid moves the cut and the areas either side absorb it.
AREA_TOLERANCE = 0.05

#: Slack on the coverage comparison. A brief with no footprint builds on the
#: whole bounding box, which is a coverage of exactly 1.0 on a rectangular
#: parcel — and exactly 1.0 is the sort of number floating point misses by an
#: ulp. Without this the default profile would refuse every plan it has ever
#: passed.
COVERAGE_TOLERANCE = 1e-9


class Gate(Protocol):
    """Something a candidate passes or fails."""

    name: str

    def check(self, plan, brief: Brief) -> bool: ...


@dataclass(frozen=True)
class _Gate:
    name: str
    _check: Callable[[object, Brief], bool]

    def check(self, plan, brief: Brief) -> bool:
        return self._check(plan, brief)


def fabric_of(plan, brief: Brief):
    """The plan's wall graph, built once and remembered.

    `to_fabric` polygonises, which is the only expensive step in the loop. The
    reachability gate and the adjacency metric both want it, so it is cached on
    the plan rather than built twice.
    """
    cached = getattr(plan, "_fabric_cache", None)
    if cached is None:
        cached = plan.to_fabric(brief.profile)
        plan._fabric_cache = cached
    return cached


def _areas_ok(plan, brief: Brief) -> bool:
    return plan.max_area_error(brief.profile) <= AREA_TOLERANCE


def _aspects_ok(plan, brief: Brief) -> bool:
    return plan.aspects_ok()


def _furniture_ok(plan, brief: Brief) -> bool:
    return all(fit_report(plan, brief.profile).values())


def _minima_ok(plan, brief: Brief) -> bool:
    """Every room at or above the code minimum AREA for its kind, on net.

    Area only. `profile.min_width` is not checked here: v1 held those as
    warnings and CLAUDE.md does not list width among the gates. A room too
    narrow to use is caught by `FURNITURE_GATE`, which measures the thing the
    width was a proxy for.

    Bands are exempt from the area *target* but not from the minimum: a
    corridor still has to be a legal corridor.
    """
    minima = brief.profile.min_area
    for cell in plan.cells:
        kind = brief.programme.by_nom(cell.nom).kind
        if kind not in minima:
            continue
        net_w, net_h = cell.net_dims(brief.profile)
        if net_w * net_h < minima[kind]:
            return False
    return True


def _coverage_ok(plan, brief: Brief) -> bool:
    """Built area over parcel area, against the profile's CES.

    CLAUDE.md lists coverage among the gates and it has never existed, for a
    reason that was structural rather than an oversight: until S14 the footprint
    *was* the parcel, so coverage was 1.0 by construction and a gate on it could
    only ever refuse or pass everything at once. Now that a footprint is chosen
    the question means something.

    Measured from the plan rather than from the brief, so a hand-built
    `PartitionPlan` is judged on what it actually covers. The parcel polygon is
    the denominator, not its bounding box — a footprint spilling into the notch
    of an L reports more than 1, which is exactly the fault to catch.
    """
    footprint = Footprint.from_envelope(plan.envelope_rect, brief.profile)
    return (
        footprint.coverage(brief.parcel)
        <= brief.profile.coverage_max + COVERAGE_TOLERANCE
    )


def daylight_capacity(cell, plan, brief: Brief) -> float:
    """Metres of legal window a cell's openable facade can take.

    For each FACADE side of the cell, the run of it lying on an openable parcel
    segment (within the same slack the fabric allows, `edge_slack`), clipped to
    the cell's clear floor; each run is worth `window_capacity` of it — jambs
    off, nothing if under the minimum window. Float arithmetic only.
    """
    profile = brief.profile
    kinds = cell.wall_kinds
    t = {side: profile.thickness_of(kinds[side].value) for side in kinds}
    net_x = (cell.x + t["left"] / 2, cell.x + cell.w - t["right"] / 2)
    net_y = (cell.y + t["bottom"] / 2, cell.y + cell.h - t["top"] / 2)
    segments = brief.parcel.openable_segments()
    total = 0.0
    for side, fixed in (
        ("left", cell.x), ("right", cell.x + cell.w),
        ("bottom", cell.y), ("top", cell.y + cell.h),
    ):
        if kinds[side] is not WallKind.FACADE:
            continue
        horizontal = side in ("bottom", "top")
        across, along = (1, 0) if horizontal else (0, 1)
        lo, hi = net_x if horizontal else net_y
        run = 0.0
        for _, a, b in segments:
            if abs(a[across] - b[across]) > TOL:          # not parallel to this side
                continue
            if abs(fixed - a[across]) > edge_slack(a, b, plan.envelope_rect, profile):
                continue
            e_lo, e_hi = sorted((a[along], b[along]))
            run += max(0.0, min(hi, e_hi) - max(lo, e_lo))
        total += window_capacity(run, profile)
    return total


def daylight_shortfall(plan, brief: Brief) -> dict[str, float]:
    """Every room the law lights, mapped to the fraction of its window it lacks
    (0.0 = lit). Rooms are those of a `DAYLIGHT_KINDS` kind: habitable rooms and
    the kitchen, decret ART. 7."""
    programme = brief.programme
    out: dict[str, float] = {}
    for cell in plan.cells:
        if programme.by_nom(cell.nom).kind not in DAYLIGHT_KINDS:
            continue
        owed = width_owed(cell.net_area(brief.profile), brief.profile)
        got = daylight_capacity(cell, plan, brief)
        out[cell.nom] = max(0.0, owed - got) / owed
    return out


def _daylight_ok(plan, brief: Brief) -> bool:
    return not any(v > 1e-9 for v in daylight_shortfall(plan, brief).values())


def _circulation_ok(plan, brief: Brief) -> bool:
    """No corridor may run past its last door by more than its own width.

    A little overrun is turning space. More than that is corridor leading
    nowhere, and it is the one circulation fault that is not a matter of
    degree — the metres are simply wasted. How *much* circulation a plan spends
    is a judgement call and stays in `metrics.py`.
    """
    try:
        report = circulation_runs(fabric_of(plan, brief))
    except (ValueError, KeyError):
        return False
    return not report.dead_ends(brief.profile.corridor_clear)


def _reachable_ok(plan, brief: Brief) -> bool:
    try:
        return reachable(fabric_of(plan, brief)).ok
    except ValueError:
        # No frontage on the entry edge, or a graph the faces disagree with.
        return False


AREA_GATE = _Gate("area", _areas_ok)
COVERAGE_GATE = _Gate("coverage", _coverage_ok)
ASPECT_GATE = _Gate("aspect", _aspects_ok)
FURNITURE_GATE = _Gate("furniture", _furniture_ok)
DAYLIGHT_GATE = _Gate("daylight", _daylight_ok)
MIN_AREA_GATE = _Gate("min_area", _minima_ok)
CIRCULATION_GATE = _Gate("circulation", _circulation_ok)
REACHABLE_GATE = _Gate("reachable", _reachable_ok)

#: The gates a candidate must pass, cheapest first. REACHABLE_GATE is last
#: because it is the one that builds the wall graph. DAYLIGHT_GATE is float
#: arithmetic on cells and parcel segments, a little dearer than the furniture
#: comparisons, so it follows them; both precede anything that builds walls.
#:
#: ASPECT_GATE is deliberately absent — see the module docstring. It is still
#: defined, so a caller who wants a stricter run can add it, but nothing in the
#: search uses it and `all_gates` does not run it.
GATES: tuple[Gate, ...] = (
    AREA_GATE,
    COVERAGE_GATE,
    MIN_AREA_GATE,
    FURNITURE_GATE,
    DAYLIGHT_GATE,
    CIRCULATION_GATE,
    REACHABLE_GATE,
)


def all_gates(plan, brief: Brief) -> tuple[bool, str | None]:
    """Run every gate in order. Returns (passed, name of the first failure)."""
    for gate in GATES:
        if not gate.check(plan, brief):
            return False, gate.name
    return True, None


# --- how far from passing --------------------------------------------------
#
# Not a score. A candidate that fails a gate is still discarded, at every
# temperature, and nothing below is ever added to `metrics.score`. What this
# answers is a different question, asked only while the search has found
# nothing valid at all: of two refused candidates, which is nearer to passing?
#
# Without it the walk was blind. `anneal` refused every candidate from a seed
# that failed its own gates and drifted at random, and on real programmes it
# never arrived anywhere: 500 proposed, 0 accepted, on an F3 of 70 m2
# (PROGRESS.md S23). Every refusal looked the same.

#: A tree that cannot be realised at all is further from passing than any tree
#: that can. Each stage outranks every amount in the stage below it.
UNREALISABLE = 1000.0

#: Candidates failing a cheap gate outrank those that only fail on the wall
#: graph: getting areas and furniture right is the larger part of the way.
CHEAP_STAGE = 100.0


def violation(plan, brief: Brief) -> float:
    """How far `plan` is from passing every gate. Zero iff `all_gates` passes.

    Staged, so the walk fixes geometry before paying for the wall graph: the
    cheap gates (area, coverage, minimum area, furniture, daylight) are measured first,
    and only a plan that clears all of them is built into a fabric and counted
    for dead ends and unreachable rooms.
    """
    profile = brief.profile
    programme = brief.programme

    cheap = sum(max(0.0, abs(e) - AREA_TOLERANCE) for e in plan.area_error(profile).values())
    footprint = Footprint.from_envelope(plan.envelope_rect, profile)
    cheap += max(0.0, footprint.coverage(brief.parcel) - profile.coverage_max - COVERAGE_TOLERANCE)
    for cell in plan.cells:
        minimum = profile.min_area.get(programme.by_nom(cell.nom).kind)
        if minimum:
            net_w, net_h = cell.net_dims(profile)
            cheap += max(0.0, minimum - net_w * net_h) / minimum
    cheap += furniture_shortfall(plan, profile)
    cheap += sum(daylight_shortfall(plan, brief).values())
    if cheap > 0.0:
        return CHEAP_STAGE + cheap

    try:
        fabric = fabric_of(plan, brief)
        runs = circulation_runs(fabric)
        report = reachable(fabric)
    except (ValueError, KeyError):
        return CHEAP_STAGE
    return float(
        len(runs.dead_ends(profile.corridor_clear))
        + len(report.unreachable)
        + len(report.through_room)
    )
