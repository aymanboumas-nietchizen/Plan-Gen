"""L3 — `fabric/`: the wall graph, and the spaces derived from it.

`WallAxis` and `WallGraph` node authored centrelines into a planar graph and
read the enclosed faces off it; `solidify` gives those faces their thickness by
the closed form in ARCHITECTURE section 2; `Space` and `FabricPlan` carry the
result down to L4 with adjacency already measured in metres of shared wall.
"""

from planfgen.fabric.axis import TOL, WallAxis, WallKind, segment_overlap
from planfgen.fabric.graph import BOUND_TOL, WallGraph
from planfgen.fabric.plan import FabricPlan, Space
from planfgen.fabric.solidify import net_polygon, wall_solids

__all__ = [
    "BOUND_TOL",
    "TOL",
    "FabricPlan",
    "Space",
    "WallAxis",
    "WallGraph",
    "WallKind",
    "net_polygon",
    "segment_overlap",
    "wall_solids",
]
