"""L4 — the R+n hook: making "do these two levels line up?" a set comparison.

Nothing calls this yet. It exists because ARCHITECTURE section 7 is right that
the three things R+n needs are nearly free now and expensive later, and this is
the third: give every stackable thing a **stable id derived from the grid**, and
comparing two levels stops being a geometry problem.

The id comes from the grid line, not from the segment. A bearing wall that runs
the width of a plan may be several axes after noding, and all of them stack
together or none do — what stacks is the line.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from planfgen.fabric.plan import FabricPlan
from planfgen.partition.grid import StructuralGrid
from planfgen.services.shaft import Shaft


#: Decimals in a stack id. Two levels cut on the same line must produce the same
#: string, so every coordinate is quantised before it is formatted.
PLACES = 2

#: How close a coordinate must be to a grid line to be called grid-aligned.
ON_GRID = 1e-6


def stable(value: float, grid: StructuralGrid, axis: str) -> float:
    """A coordinate quantised so two levels agree on it.

    Grid-aligned coordinates take the grid line exactly, which is the point of
    the structural grid: a bearing wall snapped to it on two levels gives the
    same id however the areas either side differ.

    Everything else keeps its own coordinate, rounded to the centimetre.
    Snapping unconditionally would be wrong twice over: a facade axis inset half
    a wall from the boundary is not on a grid line and would be reported as if
    it were, and on a 4.00 m module any two bearing lines within 2.00 m would
    collapse onto the same id — which would hide exactly the conflicts this
    module exists to find.
    """
    snapped = grid.snap(value, axis)
    return snapped if abs(snapped - value) <= ON_GRID else round(value, PLACES)


@dataclass
class Level:
    """One storey: its plan, its shafts, and how tall it is."""

    index: int
    height: float
    fabric: FabricPlan
    shafts: list[Shaft] = field(default_factory=list)

    def wall_stacks(self) -> set[str]:
        """Every bearing stack id on this level."""
        return {
            wall.stack_id
            for wall in self.fabric.graph.walls
            if wall.kind.bearing and wall.stack_id
        }

    def shaft_stacks(self) -> set[str]:
        return {shaft.stack_id for shaft in self.shafts if shaft.stack_id}


@dataclass(frozen=True)
class Conflict:
    """Something on one level with nothing under or over it on the other."""

    kind: str
    stack_id: str
    levels: tuple[int, int]
    detail: str


def wall_stack_id(wall, grid: StructuralGrid) -> str:
    """`V:x=3.00` for a vertical bearing line, `H:y=2.00` for a horizontal one."""
    if wall.is_horizontal:
        return f"H:y={stable(wall.p0[1], grid, 'y'):.{PLACES}f}"
    return f"V:x={stable(wall.p0[0], grid, 'x'):.{PLACES}f}"


def shaft_stack_id(shaft: Shaft, grid: StructuralGrid) -> str:
    """`SH:3.00,2.00` from the shaft's centre."""
    cx, cy = shaft.centre
    return f"SH:{stable(cx, grid, 'x'):.{PLACES}f},{stable(cy, grid, 'y'):.{PLACES}f}"


def assign_stack_ids(level: Level, grid: StructuralGrid) -> None:
    """Give every bearing wall and every shaft on this level its id.

    Partitions are left with none. Only bearing walls stack, which is the whole
    reason `WallKind.bearing` exists.
    """
    for wall in level.fabric.graph.walls:
        wall.stack_id = wall_stack_id(wall, grid) if wall.kind.bearing else None
    for shaft in level.shafts:
        shaft.stack_id = shaft_stack_id(shaft, grid)


def stack_conflicts(a: Level, b: Level) -> list[Conflict]:
    """Everything present on one level and missing on the other.

    Two identical levels conflict on nothing, which is the property the whole
    scheme rests on. `levels` is always `(a.index, b.index)`; which side is
    missing is in `detail`.
    """
    pair = (a.index, b.index)
    conflicts: list[Conflict] = []

    for kind, on_a, on_b in (
        ("wall", a.wall_stacks(), b.wall_stacks()),
        ("shaft", a.shaft_stacks(), b.shaft_stacks()),
    ):
        for stack_id in sorted(on_a - on_b):
            conflicts.append(
                Conflict(kind, stack_id, pair,
                         f"on level {a.index}, nothing under it on level {b.index}")
            )
        for stack_id in sorted(on_b - on_a):
            conflicts.append(
                Conflict(kind, stack_id, pair,
                         f"on level {b.index}, nothing under it on level {a.index}")
            )
    return conflicts
