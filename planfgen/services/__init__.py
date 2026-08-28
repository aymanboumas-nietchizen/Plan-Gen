"""L4 — `services/`: shafts, wet walls, and the hooks R+n will need.

A shaft is an object with a position, not a property of a room, so two levels
can be asked whether theirs line up. Every bearing wall and every shaft carries
a stable id derived from the structural grid, which turns that question into a
set comparison. Nothing calls `stack_conflicts` yet — ARCHITECTURE section 7.
"""

from planfgen.services.shaft import (
    SHAFT_SIDE,
    Shaft,
    ShaftType,
    place_shafts,
    wet_clusters,
)
from planfgen.services.stacking import (
    Conflict,
    Level,
    assign_stack_ids,
    shaft_stack_id,
    stack_conflicts,
    stable,
    wall_stack_id,
)
from planfgen.services.wet import assign_wet_walls, wet_report

__all__ = [
    "SHAFT_SIDE",
    "Conflict",
    "Level",
    "Shaft",
    "ShaftType",
    "assign_stack_ids",
    "assign_wet_walls",
    "place_shafts",
    "shaft_stack_id",
    "stable",
    "stack_conflicts",
    "wall_stack_id",
    "wet_clusters",
    "wet_report",
]
