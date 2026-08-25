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
from dataclasses import dataclass, field

from planfgen.brief.footprint import Footprint
from planfgen.brief.plan import Brief
from planfgen.evaluate.constraints import all_gates
from planfgen.evaluate.metrics import Scores, score
from planfgen.partition.grid import StructuralGrid
from planfgen.partition.plan import PartitionPlan
from planfgen.partition.tree import SlicingTree
from planfgen.search.moves import mutate, mutate_brief
from planfgen.topology.relations import ProgrammeGraph

#: How many of the best candidates a run hands back.
KEEP_BEST = 10

#: While no valid candidate has been found, the chance of jumping back to the
#: seed rather than drifting further. Without it the walk diverges: measured at
#: 0 valid plans in 200 iterations on the v1 brief, against 25 with it.
RESTART = 0.35

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


def evaluate(
    tree: SlicingTree,
    brief: Brief,
    grid: StructuralGrid,
    graph: ProgrammeGraph | None,
    iteration: int,
) -> Result | None:
    """Realise, gate, and score. `None` means the candidate was discarded."""
    try:
        plan = tree.realise(envelope_of(brief), brief, grid)
    except ValueError:
        return None
    passed, _failure = all_gates(plan, brief)
    if not passed:
        return None
    return Result(tree=tree, plan=plan, scores=score(plan, brief, graph), iteration=iteration)


def _why(tree: SlicingTree, brief: Brief, grid: StructuralGrid) -> str:
    """The gate that turned a candidate away, for the run statistics."""
    try:
        plan = tree.realise(envelope_of(brief), brief, grid)
    except ValueError:
        return "unrealisable"
    _passed, failure = all_gates(plan, brief)
    return failure or "none"


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

    current = evaluate(tree0, brief, grid_for(brief), graph, 0)
    best: list[Result] = [current] if current else []
    if n_iter <= 0:
        return best

    # A band is named from a circulation room, so the programme sets how many
    # the search may propose.
    band_budget = max(1, len(brief.programme.circulation_rooms))

    ratio = (t1 / t0) ** (1.0 / max(1, n_iter - 1)) if t0 > 0 else 1.0
    temperature = t0
    walk = current.tree if current else tree0
    walk_brief = current.brief if current else brief
    movable = brief.footprint is not None

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
        candidate = evaluate(candidate_tree, candidate_brief, grid, graph, iteration)

        if candidate is None:
            stats.reject(_why(candidate_tree, candidate_brief, grid))
            # Nothing valid has been found yet, so there is no hill to climb.
            # Drift, so a seed that fails its own gates is not mutated forever
            # in place — but restart from the seed often enough that the walk
            # cannot wander off into ever stranger trees, which is what an
            # unbounded random walk does and it never comes back.
            if current is None:
                if rng.random() < RESTART:
                    walk = tree0
                else:
                    walk = candidate_tree
                # The restart is on the *tree* only. Its job is to stop an
                # unbounded walk wandering into ever stranger trees, and the
                # footprint is neither unbounded nor high-dimensional — throwing
                # it away too would mean the building could never travel from
                # the proportion it was fitted at to one that works, which on a
                # long thin parcel is the whole difficulty.
                walk_brief = candidate_brief
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
