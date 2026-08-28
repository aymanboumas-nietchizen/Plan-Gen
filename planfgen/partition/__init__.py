"""L2 — `partition/`: the slicing tree, and the exact tiling it realises.

The structural grid, binary cuts, the ternary band cut, the net/gross
inversion and `PartitionPlan`.
"""

from planfgen.partition.bridge import to_fabric, to_wall_graph
from planfgen.partition.grid import StructuralGrid
from planfgen.partition.plan import PartitionPlan, SpaceCell
from planfgen.partition.sizing import aspect_ok, axis_dims
from planfgen.partition.tree import (
    BandCut,
    Cut,
    Direction,
    EnvelopeTooTight,
    Leaf,
    Node,
    SlicingTree,
    UnrealisableTree,
)

__all__ = [
    "BandCut",
    "Cut",
    "Direction",
    "EnvelopeTooTight",
    "Leaf",
    "Node",
    "PartitionPlan",
    "SlicingTree",
    "SpaceCell",
    "StructuralGrid",
    "UnrealisableTree",
    "aspect_ok",
    "axis_dims",
    "to_fabric",
    "to_wall_graph",
]
