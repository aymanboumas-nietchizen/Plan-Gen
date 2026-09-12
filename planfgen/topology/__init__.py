"""L1 — `topology/`: typed relations, an access gradient, and zoning.

The stage that decides what the plan has to be, before anything decides where.
"""

from planfgen.topology.gradient import Zone, access_gradient, depths, zone_of
from planfgen.topology.plan import TopologyPlan
from planfgen.topology.relations import (
    ProgrammeGraph,
    Relation,
    RelationType,
)
from planfgen.topology.zoning import (
    AFFINITY,
    day_night,
    suggest_tree_order,
    wet_cluster,
)

__all__ = [
    "AFFINITY",
    "ProgrammeGraph",
    "Relation",
    "RelationType",
    "TopologyPlan",
    "Zone",
    "access_gradient",
    "day_night",
    "depths",
    "suggest_tree_order",
    "wet_cluster",
    "zone_of",
]
