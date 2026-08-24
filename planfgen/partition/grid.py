"""L2a — the structural grid that bearing walls are allowed to sit on.

ARCHITECTURE section 5: a structural cut snaps to a grid line and the areas
either side absorb the tolerance; a partition cut is free and its leaf areas
come out exact. Two levels can only align if both were cut on the same
structural lines, which is what makes R+n cost nothing to honour now.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Grid arithmetic tolerance, in metres.
GRID_TOL = 1e-9


@dataclass(frozen=True)
class StructuralGrid:
    """A rectangular module the bearing walls of every level share."""

    origin: tuple[float, float]
    module_x: float
    module_y: float

    def __post_init__(self) -> None:
        if self.module_x <= 0 or self.module_y <= 0:
            raise ValueError(
                f"grid modules must be positive, got {self.module_x} x {self.module_y}"
            )

    def _module(self, axis: str) -> tuple[float, float]:
        if axis == "x":
            return self.origin[0], self.module_x
        if axis == "y":
            return self.origin[1], self.module_y
        raise ValueError(f"unknown axis {axis!r}; expected 'x' or 'y'")

    def snap(self, value: float, axis: str) -> float:
        """The nearest grid line on this axis."""
        origin, module = self._module(axis)
        return origin + round((value - origin) / module) * module

    def _lines(self, axis: str, lo: float, hi: float) -> list[float]:
        origin, module = self._module(axis)
        first = math.ceil((lo - origin) / module - GRID_TOL)
        last = math.floor((hi - origin) / module + GRID_TOL)
        return [origin + i * module for i in range(first, last + 1)]

    def lines_x(self, lo: float, hi: float) -> list[float]:
        """Every vertical grid line in [lo, hi]."""
        return self._lines("x", lo, hi)

    def lines_y(self, lo: float, hi: float) -> list[float]:
        """Every horizontal grid line in [lo, hi]."""
        return self._lines("y", lo, hi)

    @classmethod
    def from_span(
        cls,
        width: float,
        height: float,
        max_span: float = 5.0,
        origin: tuple[float, float] = (0.0, 0.0),
    ) -> StructuralGrid:
        """The coarsest grid no bay of which exceeds `max_span`.

        Taking `n = ceil(span / max_span)` bays and dividing gives the largest
        module at or under the limit that divides the span exactly, so the grid
        never leaves a ragged bay at one end.
        """
        if width <= 0 or height <= 0:
            raise ValueError(f"span must be positive, got {width} x {height}")
        if max_span <= 0:
            raise ValueError(f"max_span must be positive, got {max_span}")
        return cls(
            origin=origin,
            module_x=width / math.ceil(width / max_span - GRID_TOL),
            module_y=height / math.ceil(height / max_span - GRID_TOL),
        )
