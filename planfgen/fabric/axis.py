"""L3a — the wall axis: the authored primitive everything else is derived from.

An axis is a centreline, not a solid. It carries no thickness: thickness is a
regulatory property looked up per kind through `RegulationProfile.thickness_of`,
so a plan can be re-solidified against a different profile without touching the
graph. Axes are horizontal or vertical and nothing else — the whole project is
axis-aligned, and a diagonal here would silently break face extraction, net-area
correction and the door-run measurement further down the stack.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

#: Geometric tolerance for the axis-alignment and collinearity predicates.
TOL = 1e-9


class WallKind(Enum):
    """What a wall is for. Thickness is *not* stored here — see the module docstring."""

    FACADE = "facade"
    PORTEUR = "porteur"
    CLOISON = "cloison"
    WET = "wet"

    @property
    def bearing(self) -> bool:
        """True if this wall carries load, and so is the kind that can stack.

        Only bearing walls align between levels; ARCHITECTURE section 7 depends
        on the distinction existing from the start.
        """
        return self in _BEARING


_BEARING = frozenset({WallKind.FACADE, WallKind.PORTEUR})


def segment_overlap(
    p0: tuple[float, float],
    p1: tuple[float, float],
    q0: tuple[float, float],
    q1: tuple[float, float],
) -> float:
    """Metres of shared run between two collinear axis-aligned segments.

    Returns 0.0 unless the two are parallel, collinear and genuinely overlap;
    segments that merely touch at a point share no run. Plain float arithmetic —
    this is called in inner loops and must not reach for Shapely.
    """
    p_horizontal = abs(p1[1] - p0[1]) <= TOL
    q_horizontal = abs(q1[1] - q0[1]) <= TOL
    p_vertical = abs(p1[0] - p0[0]) <= TOL
    q_vertical = abs(q1[0] - q0[0]) <= TOL

    if p_horizontal and q_horizontal:
        if abs(p0[1] - q0[1]) > TOL:
            return 0.0
        axis = 0
    elif p_vertical and q_vertical:
        if abs(p0[0] - q0[0]) > TOL:
            return 0.0
        axis = 1
    else:
        return 0.0

    lo = max(min(p0[axis], p1[axis]), min(q0[axis], q1[axis]))
    hi = min(max(p0[axis], p1[axis]), max(q0[axis], q1[axis]))
    return max(0.0, hi - lo)


@dataclass
class WallAxis:
    """One straight run of wall centreline, horizontal or vertical.

    Endpoints are normalised so that `p0 <= p1` lexicographically: an axis is
    undirected, and a canonical order keeps splitting and overlap deterministic.
    Mutable so that L4 can assign `stack_id` in place once shafts are known.
    """

    p0: tuple[float, float]
    p1: tuple[float, float]
    kind: WallKind
    stack_id: str | None = None

    def __post_init__(self) -> None:
        self.p0 = (float(self.p0[0]), float(self.p0[1]))
        self.p1 = (float(self.p1[0]), float(self.p1[1]))
        dx = abs(self.p1[0] - self.p0[0])
        dy = abs(self.p1[1] - self.p0[1])
        if dx <= TOL and dy <= TOL:
            raise ValueError(f"zero-length wall axis at {self.p0}")
        if dx > TOL and dy > TOL:
            raise ValueError(
                f"diagonal wall axis {self.p0} -> {self.p1}; this project is "
                f"axis-aligned only"
            )
        if self.p1 < self.p0:
            self.p0, self.p1 = self.p1, self.p0

    @property
    def length(self) -> float:
        return abs(self.p1[0] - self.p0[0]) + abs(self.p1[1] - self.p0[1])

    @property
    def is_horizontal(self) -> bool:
        return abs(self.p1[1] - self.p0[1]) <= TOL

    @property
    def is_vertical(self) -> bool:
        return abs(self.p1[0] - self.p0[0]) <= TOL

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(minx, miny, maxx, maxy)."""
        return (
            min(self.p0[0], self.p1[0]),
            min(self.p0[1], self.p1[1]),
            max(self.p0[0], self.p1[0]),
            max(self.p0[1], self.p1[1]),
        )

    def collinear_overlap(self, other: WallAxis) -> float:
        """Metres of shared run with another axis; 0.0 if not collinear."""
        return segment_overlap(self.p0, self.p1, other.p0, other.p1)
