"""Beside the stack — `search/`: mutations on the tree, and annealing.

The search space is L1 and L2 only: which room goes in which leaf, how the tree
is shaped, and which cuts are structural. L3 to L8 are deterministic refinements
of whatever it settles on.
"""

from planfgen.search.anneal import (
    KEEP_BEST,
    Result,
    RunStats,
    anneal,
    envelope_of,
    evaluate,
    grid_for,
)
from planfgen.search.moves import (
    MOVES,
    flip_cut,
    insert_band,
    mutate,
    remove_band,
    regroup,
    rotate_band,
    slide_cut,
    swap_leaves,
)

__all__ = [
    "KEEP_BEST",
    "MOVES",
    "Result",
    "RunStats",
    "anneal",
    "envelope_of",
    "evaluate",
    "flip_cut",
    "insert_band",
    "grid_for",
    "mutate",
    "regroup",
    "remove_band",
    "rotate_band",
    "slide_cut",
    "swap_leaves",
]
