"""Simulated annealing over slicing trees.

v1 used random restart: throw away everything learned and start again. This
keeps the current tree and mutates it, accepting a worse candidate with a
probability that falls as the run cools, so a plan can get worse on the way to
getting better.

A candidate that fails a gate costs infinity, not a penalty. That is the whole
point of the hard/soft split in CLAUDE.md: a 7 m2 chambre is not a plan with a
low score, and letting it compete on points is how a search ends up proposing
one.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace

from planfgen.brief.footprint import Footprint, fit_footprint, party_span, place_footprint
from planfgen.brief.plan import Brief, InfeasibleBrief
from planfgen.evaluate.constraints import UNREALISABLE, all_gates, violation
from planfgen.evaluate.metrics import Scores, score
from planfgen.partition.grid import StructuralGrid
from planfgen.partition.plan import PartitionPlan
from planfgen.partition.tree import SlicingTree
from planfgen.search.moves import mutate, mutate_brief
from planfgen.topology.relations import ProgrammeGraph

#: How many of the best candidates a run hands back.
KEEP_BEST = 10

#: While no valid candidate has been found, the chance of jumping back to the
#: seed rather than walking on. Without any return the walk diverges (0 valid
#: plans in 200 iterations on the v1 brief, 25 with a return at 0.35).
#:
#: The walk is guided now — see `UPHILL` and `violation` — and was tried
#: returning to the nearest tree it had found instead of to the seed. That lost:
#: a seed a few moves from valid is the commonest case, and the nearest-so-far
#: walked away from it. Measured 2026-09-28 on 72 real-programme runs, a 26 x 12
#: m parcel at aspect 1.25 (3 seeds) and the studio's corridorless programme (4):
#:
#:     blind, return 0.35 (before)          23 / 72    3 / 3    4 / 4
#:     guided, return to nearest 0.05       25 / 72    1 / 3    2 / 4
#:     guided, return to seed 0.35          25 / 72    3 / 3    4 / 4
#:     guided, return to seed 0.50          26 / 72    3 / 3    4 / 4   <- this
RESTART = 0.50

#: While nothing is valid, the chance of taking a step that moves further from
#: passing. At 0.10 and above the walk is nearly blind again (21 / 72 at 0.30).
UPHILL = 0.05

#: How often the search moves the *building* rather than the plan inside it.
#: Only ever on a brief that has a footprint — one without builds on its whole
#: parcel, and shrinking it behind the caller's back would answer a different
#: question. Kept low because `shape_footprint` re-solves, which costs a
#: `fit_footprint`; measured at 0.20 the run is about a third dearer per
#: candidate than a tree-only search.
P_FOOTPRINT = 0.20

#: And how often before anything has passed a gate. Zero, and measured rather
#: than assumed: while nothing is valid the *tree* is what the gates are
#: refusing, and every footprint move is a tree move not taken.
#:
#: It is a constant rather than a plain `if` because the measurement is worth
#: keeping. Raised to 0.30 it does rescue the case it was meant to — a building
#: fitted to the proportion of a long thin parcel comes out a strip that no
#: arrangement can furnish, and 26 x 12 m went from 0 of 12 seeds finding a plan
#: to 5 of 12 — but it costs about a tenth of the score on ordinary parcels,
#: which is the worse trade. The real fix is not to fit a strip in the first
#: place; see PROGRESS.md, and S18's reference plans.
P_FOOTPRINT_COLD = 0.0


@dataclass(frozen=True)
class Result:
    """One candidate that passed every gate, and what it scored."""

    tree: SlicingTree
    plan: PartitionPlan
    scores: Scores
    iteration: int

    @property
    def cost(self) -> float:
        return 1.0 - self.scores.globale

    @property
    def brief(self) -> Brief:
        """What this candidate was built to. Not necessarily the brief handed
        to `anneal`: the footprint is a search variable too."""
        return self.plan.brief


@dataclass
class RunStats:
    """What the run did, which is worth as much as what it found."""

    proposed: int = 0
    accepted: int = 0
    rejected_by: dict[str, int] = field(default_factory=dict)

    def reject(self, gate: str) -> None:
        self.rejected_by[gate] = self.rejected_by.get(gate, 0) + 1

    def explain(self) -> str:
        failures = ", ".join(
            f"{gate} {n}" for gate, n in sorted(self.rejected_by.items())
        )
        return (
            f"{self.proposed} proposed, {self.accepted} accepted"
            + (f"; rejected by {failures}" if failures else "")
        )


def envelope_of(brief: Brief) -> tuple[float, float, float, float]:
    """The rect a tree is realised on: the footprint inset by half the facade.

    That inset is what puts the facade *solids* inside the built extent and what
    makes L2's net areas reconcile with L0's feasibility interior.

    A brief with no footprint builds on the whole parcel, which was the only
    behaviour before S14 and is still what every brief that has not been through
    `fit_brief` gets. `Footprint.of_parcel` is that bounding box, so the two
    branches are the same arithmetic and not two definitions of an envelope.
    """
    return _footprint_of(brief).envelope_rect(brief.profile)


def grid_for(brief: Brief) -> StructuralGrid:
    """The structural grid the bearing walls may sit on.

    Aligned to the footprint, not to the parcel: a grid whose origin is a
    boundary the building does not touch would snap structural cuts to lines
    that mean nothing on site.
    """
    footprint = _footprint_of(brief)
    return StructuralGrid.from_span(
        footprint.w, footprint.h, origin=(footprint.x, footprint.y)
    )


def _footprint_of(brief: Brief) -> Footprint:
    return brief.footprint or Footprint.of_parcel(brief.parcel)


#: Two footprints whose sides agree to this, in m, are the same building: the
#: re-solve for a tree keeps the current one, and with it wherever
#: `slide_footprint` put it.
SAME_SIZE = 1e-4


def refit(tree: SlicingTree, brief: Brief, cache: dict | None = None) -> Brief:
    """The envelope follows the tree: `brief` with its footprint re-solved for `tree`.

    A band's area is an output, so a tree with more (or longer) corridor than
    the one the footprint was solved for steals it from the rooms: on the
    F3/F4 seed footprints every two-band tree missed its areas by 4.5-9 %
    against a 5 % gate, and no degagement could ever be accepted (S27). So
    each candidate is realised on a footprint solved for itself — spanning the
    party walls if the current one does, else at the current proportion — and
    placed by `place_footprint`. Where the solve lands on the current size, the
    current footprint is kept as it stands.

    A brief with no footprint builds on its parcel and is returned as is; so is
    one the tree cannot be fitted to (the gates then judge it as it stands).
    `cache` maps (tree, proportion) to the solve, so a tree revisited costs
    nothing; `fit_footprint` realises the tree several times.
    """
    footprint = brief.footprint
    if footprint is None:
        return brief
    span_w, span_d = party_span(brief.parcel)
    spans = (span_w is not None and abs(footprint.w - span_w) <= SAME_SIZE) or (
        span_d is not None and abs(footprint.h - span_d) <= SAME_SIZE
    )
    aspect = None if spans else footprint.aspect
    key = (tree, None if aspect is None else round(aspect, 9))
    if cache is not None and key in cache:
        solved = cache[key]
    else:
        solved = _solve(tree, brief, aspect)
        if cache is not None:
            cache[key] = solved
    if solved is None:
        return brief
    size, placed = solved
    if abs(size.w - footprint.w) <= SAME_SIZE and abs(size.h - footprint.h) <= SAME_SIZE:
        return brief
    return replace(brief, footprint=placed)


def _solve(
    tree: SlicingTree, brief: Brief, aspect: float | None
) -> tuple[Footprint, Footprint] | None:
    """(solved size, where it stands), or None if the tree cannot be fitted."""
    try:
        solved = fit_footprint(brief.programme, brief.parcel, brief.profile, tree, aspect)
    except (ValueError, InfeasibleBrief):
        return None
    placed = place_footprint(solved, brief.parcel)
    return solved, placed if placed.buildable(brief.parcel) else solved


def evaluate(
    tree: SlicingTree,
    brief: Brief,
    grid: StructuralGrid,
    graph: ProgrammeGraph | None,
    iteration: int,
) -> Result | None:
    """Refit, realise, gate, and score. `None` means the candidate was discarded.

    The footprint is re-solved for `tree` (`refit`), so the result's brief may
    not be `brief`: read it off `Result.brief`.
    """
    return _assess(tree, brief, grid, graph, iteration, measure=False)[0]


def _assess(
    tree: SlicingTree,
    brief: Brief,
    grid: StructuralGrid,
    graph: ProgrammeGraph | None,
    iteration: int,
    measure: bool,
    fits: dict | None = None,
) -> tuple[Result | None, str | None, float]:
    """One realise for everything the loop wants to know about a candidate.

    Returns the result (or None), the first gate that refused it, and — when
    `measure` — how far it is from passing. The distance is only asked for
    while nothing valid has been found; after that the gates alone decide.
    The candidate is realised on its own footprint (`refit`; `fits` caches it).
    """
    fitted = refit(tree, brief, fits)
    if fitted is not brief:
        brief, grid = fitted, grid_for(fitted)
    try:
        plan = tree.realise(envelope_of(brief), brief, grid)
    except ValueError:
        return None, "unrealisable", UNREALISABLE
    passed, failure = all_gates(plan, brief)
    if not passed:
        return None, failure, violation(plan, brief) if measure else 0.0
    result = Result(tree=tree, plan=plan, scores=score(plan, brief, graph), iteration=iteration)
    return result, None, 0.0


def anneal(
    brief: Brief,
    tree0: SlicingTree,
    n_iter: int,
    t0: float = 1.0,
    t1: float = 0.01,
    seed: int = 0,
    graph: ProgrammeGraph | None = None,
    stats: RunStats | None = None,
) -> list[Result]:
    """Anneal from `tree0` and return the best candidates seen, best first.

    The same seed always gives the same run. Temperature falls geometrically
    from `t0` to `t1`; a candidate that fails a gate is not a worse candidate
    but no candidate at all, so it is never accepted at any temperature.
    """
    rng = random.Random(seed)
    stats = stats if stats is not None else RunStats()

    fits: dict = {}
    current, _, start_violation = _assess(
        tree0, brief, grid_for(brief), graph, 0, measure=True, fits=fits
    )
    best: list[Result] = [current] if current else []
    if n_iter <= 0:
        return best

    # A band is named from a *spare* circulation room, so the programme and the
    # leaf set together set how many the search may propose. This was
    # `max(1, len(circulation_rooms))`, which let a programme with no corridor
    # at all propose one band, and a band nobody can name is a candidate that
    # cannot be realised at any envelope — proposals spent to buy a refusal.
    # Every move preserves the leaf set, so this figure holds along the walk.
    band_budget = len(tree0.band_names(brief.programme))

    ratio = (t1 / t0) ** (1.0 / max(1, n_iter - 1)) if t0 > 0 else 1.0
    temperature = t0
    walk = current.tree if current else tree0
    walk_brief = current.brief if current else brief
    movable = brief.footprint is not None
    # While nothing is valid: how far the walk is from passing. See `violation`
    # — this steers, it never scores.
    walk_violation = start_violation

    for iteration in range(1, n_iter + 1):
        chance = P_FOOTPRINT if current is not None else P_FOOTPRINT_COLD
        if movable and rng.random() < chance:
            candidate_tree = walk
            candidate_brief = mutate_brief(walk_brief, walk, rng)
        else:
            candidate_tree = mutate(walk, rng, grid_for(walk_brief), band_budget)
            candidate_brief = walk_brief
        grid = grid_for(candidate_brief)
        stats.proposed += 1
        candidate, failure, distance = _assess(
            candidate_tree, candidate_brief, grid, graph, iteration,
            measure=current is None, fits=fits,
        )

        if candidate is None:
            stats.reject(failure)
            # Nothing valid has been found yet, so there is no score to climb —
            # but there is a distance to close. Step when the candidate is no
            # further from passing than the walk, and now and then when it is;
            # otherwise, often, go back to the seed rather than wander.
            #
            # The return is on the *tree* only. The footprint is neither
            # unbounded nor high-dimensional, and throwing it away too would
            # mean the building could never travel from the proportion it was
            # fitted at to one that works — on a long thin parcel, the whole
            # difficulty.
            if current is None:
                if distance <= walk_violation or rng.random() < UPHILL:
                    walk, walk_brief, walk_violation = (
                        candidate_tree, candidate_brief, distance
                    )
                elif rng.random() < RESTART:
                    walk, walk_violation = tree0, start_violation
        else:
            if current is None or _accept(candidate.cost - current.cost, temperature, rng):
                current = candidate
                walk, walk_brief = candidate.tree, candidate.brief
                stats.accepted += 1
            best.append(candidate)
            best.sort(key=lambda r: r.cost)
            del best[KEEP_BEST:]

        temperature *= ratio

    return best


def _accept(delta: float, temperature: float, rng: random.Random) -> bool:
    """Downhill always; uphill with a probability that falls as it cools."""
    if delta <= 0:
        return True
    return rng.random() < math.exp(-delta / max(temperature, 1e-9))
