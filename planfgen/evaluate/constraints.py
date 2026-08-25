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

The gates run cheapest first and the first failure wins, so a candidate that
fails on a float comparison never pays for the wall graph. Building the fabric
is by far the most expensive thing here, and only `REACHABLE_GATE` needs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from planfgen.brief.plan import Brief
from planfgen.circulation.reachable import reachable
from planfgen.circulation.shape import circulation_runs
from planfgen.habitability.check import fit_report

#: How far a room's net area may miss its target and still be a plan, as a
#: fraction. Free cuts are exact, so this slack exists for structural ones,
#: where the grid moves the cut and the areas either side absorb it.
AREA_TOLERANCE = 0.05


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
ASPECT_GATE = _Gate("aspect", _aspects_ok)
FURNITURE_GATE = _Gate("furniture", _furniture_ok)
MIN_AREA_GATE = _Gate("min_area", _minima_ok)
CIRCULATION_GATE = _Gate("circulation", _circulation_ok)
REACHABLE_GATE = _Gate("reachable", _reachable_ok)

#: The gates a candidate must pass, cheapest first. REACHABLE_GATE is last
#: because it is the one that builds the wall graph.
#:
#: ASPECT_GATE is deliberately absent — see the module docstring. It is still
#: defined, so a caller who wants a stricter run can add it, but nothing in the
#: search uses it and `all_gates` does not run it.
GATES: tuple[Gate, ...] = (
    AREA_GATE,
    MIN_AREA_GATE,
    FURNITURE_GATE,
    CIRCULATION_GATE,
    REACHABLE_GATE,
)


def all_gates(plan, brief: Brief) -> tuple[bool, str | None]:
    """Run every gate in order. Returns (passed, name of the first failure)."""
    for gate in GATES:
        if not gate.check(plan, brief):
            return False, gate.name
    return True, None
