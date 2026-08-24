"""L2 — `partition/`: the slicing tree, and the exact tiling it realises.

L2a, in place: the structural grid, binary cuts, the net/gross inversion and
`PartitionPlan`. The band cut is L2b and does not exist yet.
"""

from planfgen.partition.grid import StructuralGrid
from planfgen.partition.plan import PartitionPlan, SpaceCell
from planfgen.partition.sizing import aspect_ok, axis_dims
from planfgen.partition.tree import Cut, Direction, Leaf, Node, SlicingTree

__all__ = [
    "Cut",
    "Direction",
    "Leaf",
    "Node",
    "PartitionPlan",
    "SlicingTree",
    "SpaceCell",
    "StructuralGrid",
    "aspect_ok",
    "axis_dims",
]
