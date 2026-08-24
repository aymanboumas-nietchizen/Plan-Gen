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

from planfgen.brief.plan import Brief
from planfgen.evaluate.constraints import all_gates
from planfgen.evaluate.metrics import Scores, score
from planfgen.partition.grid import StructuralGrid
from planfgen.partition.plan import PartitionPlan
from planfgen.partition.tree import SlicingTree
from planfgen.search.moves import mutate
from planfgen.topology.relations import ProgrammeGraph

#: How many of the best candidates a run hands back.
KEEP_BEST = 10

#: While no valid candidate has been found, the chance of jumping back to the
#: seed rather than drifting further. Without it the walk diverges: measured at
#: 0 valid plans in 200 iterations on the v1 brief, against 25 with it.
RESTART = 0.35


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
    """The rect a tree is realised on: the parcel inset by half the facade.

    That inset is what puts the facade *solids* inside the boundary and what
    makes L2's net areas reconcile with L0's feasibility interior.
    """
    inset = brief.profile.facade_t / 2
    minx, miny, maxx, maxy = brief.parcel.outline.bounds
    return (minx + inset, miny + inset, (maxx - minx) - 2 * inset, (maxy - miny) - 2 * inset)


def grid_for(brief: Brief) -> StructuralGrid:
    minx, miny, maxx, maxy = brief.parcel.outline.bounds
    return StructuralGrid.from_span(maxx - minx, maxy - miny, origin=(minx, miny))


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
    grid = grid_for(brief)
    stats = stats if stats is not None else RunStats()

    current = evaluate(tree0, brief, grid, graph, 0)
    best: list[Result] = [current] if current else []
    if n_iter <= 0:
        return best

    ratio = (t1 / t0) ** (1.0 / max(1, n_iter - 1)) if t0 > 0 else 1.0
    temperature = t0
    walk = current.tree if current else tree0

    for iteration in range(1, n_iter + 1):
        candidate_tree = mutate(walk, rng, grid)
        stats.proposed += 1
        candidate = evaluate(candidate_tree, brief, grid, graph, iteration)

        if candidate is None:
            stats.reject(_why(candidate_tree, brief, grid))
            # Nothing valid has been found yet, so there is no hill to climb.
            # Drift, so a seed that fails its own gates is not mutated forever
            # in place — but restart from the seed often enough that the walk
            # cannot wander off into ever stranger trees, which is what an
            # unbounded random walk does and it never comes back.
            if current is None:
                walk = tree0 if rng.random() < RESTART else candidate_tree
        else:
            if current is None or _accept(candidate.cost - current.cost, temperature, rng):
                current, walk = candidate, candidate.tree
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
