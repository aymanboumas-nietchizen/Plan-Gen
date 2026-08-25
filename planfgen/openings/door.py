"""L6 — a door is an interval on a wall, plus the space its leaf needs.

CLAUDE.md: openings are intervals hosted on a wall. Not a link between two rooms
and not a symbol dropped on a drawing — a run of wall, of a stated width, at a
stated position, with a quarter-disc of floor in front of it that nothing else
may occupy. The clearance is the part v1 had no way to express, and it is the
part that decides whether two doors can share a wall.
"""

from __future__ import annotations

from dataclasses import dataclass

from planfgen.brief.regulation import RegulationProfile
from planfgen.fabric.axis import WallAxis

#: The front door is wider than an internal one. The value itself belongs to the
#: regulation profile — CLAUDE.md keeps every regulation number in one file — so
#: this name is the profile's own default, read once, rather than a second copy
#: of it that could drift.
ENTRY_LEAF = RegulationProfile.__dataclass_fields__["entry_leaf"].default


@dataclass
class Door:
    """One door. `t` is its centre along the wall, from 0 at `p0` to 1 at `p1`.

    `swing_side` is not in the layer's brief but has to be here: a door knows
    its wall and the *name* of the room it opens into, and a name is not a
    direction. Without it `clearance_box` could not say which side of the wall
    the leaf sweeps. It is +1 for the wall's left normal and -1 for its right.
    """

    wall: WallAxis
    t: float
    leaf: float
    swing_into: str
    hinge: str = "low"
    swing_side: int = 1

    def __post_init__(self) -> None:
        if not 0.0 <= self.t <= 1.0:
            raise ValueError(f"a door sits along its wall, 0..1, not at {self.t}")
        if self.leaf <= 0:
            raise ValueError(f"leaf must be positive, got {self.leaf}")
        if self.hinge not in ("low", "high"):
            raise ValueError(f"hinge is 'low' or 'high', not {self.hinge!r}")

    @property
    def span(self) -> tuple[float, float]:
        """The interval the opening occupies along the wall, in metres."""
        centre = self.t * self.wall.length
        return (centre - self.leaf / 2, centre + self.leaf / 2)

    def position(self) -> tuple[float, float]:
        """The centre of the opening, in plan coordinates."""
        (x0, y0), (x1, y1) = self.wall.p0, self.wall.p1
        return (x0 + self.t * (x1 - x0), y0 + self.t * (y1 - y0))

    def clearance_box(self) -> tuple[float, float, float, float]:
        """(minx, miny, maxx, maxy) of the quarter-disc the leaf sweeps.

        The leaf turns about the hinge through a right angle, so it sweeps a
        quarter-disc of radius `leaf`. Its bounding rectangle is the opening's
        own interval along the wall by `leaf` deep on the swing side — which is
        why two doors clear each other exactly when their openings do not
        overlap on the same side.
        """
        low, high = self.span
        (x0, y0), (x1, y1) = self.wall.p0, self.wall.p1
        depth = self.leaf * (1 if self.swing_side >= 0 else -1)
        if self.wall.is_horizontal:
            near, far = sorted((y0, y0 + depth))
            return (x0 + low, near, x0 + high, far)
        near, far = sorted((x0, x0 + depth))
        return (near, y0 + low, far, y0 + high)

    def clashes_with(self, other: Door) -> bool:
        """True if the two leaves want the same floor."""
        a, b = self.clearance_box(), other.clearance_box()
        return not (
            a[2] <= b[0] + 1e-9
            or b[2] <= a[0] + 1e-9
            or a[3] <= b[1] + 1e-9
            or b[3] <= a[1] + 1e-9
        )


def free_slot(wall: WallAxis, taken: list[Door], leaf: float, jamb: float) -> float | None:
    """A centre `t` on this wall where a leaf fits clear of the doors already on it.

    Walks the wall in jamb-sized steps rather than solving, because a wall
    carries one or two doors and a loop of twenty float comparisons is cheaper
    than being clever about it.
    """
    module = leaf + 2 * jamb
    if wall.length < module:
        return None
    steps = max(1, int((wall.length - module) / max(jamb, 1e-6)) + 1)
    for step in range(steps):
        low = jamb + step * jamb
        if low + leaf + jamb > wall.length:
            break
        t = (low + leaf / 2) / wall.length
        probe = Door(wall, t, leaf, "", "low")
        if not any(probe.clashes_with(other) for other in taken):
            return t
    return None
