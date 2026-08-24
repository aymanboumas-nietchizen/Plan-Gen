"""L3 — `fabric/`: the wall graph, and the spaces derived from it.

L3a, in place: `WallAxis` and `WallGraph`, which node authored axes into a
planar graph and read the enclosed faces back off it. Solidification, `Space`
and `FabricPlan` are L3b and do not exist yet.
"""

from planfgen.fabric.axis import TOL, WallAxis, WallKind, segment_overlap
from planfgen.fabric.graph import BOUND_TOL, WallGraph

__all__ = [
    "BOUND_TOL",
    "TOL",
    "WallAxis",
    "WallGraph",
    "WallKind",
    "segment_overlap",
]
