"""L6 — a window is an interval on a wall, and only where the edge allows one.

CLAUDE.md: openings are legal only where the parcel edge allows. A window on a
`MITOYEN` is not a worse plan, it is a wall through somebody else's building —
which is why the check lives here, on the parcel edge, and not in a score.

How much glass a room needs is `daylight_ratio` of its net floor. How wide that
makes the window follows from the head and allege heights, which are regulation
values and therefore live in `brief/regulation.py`, not here.
"""

from __future__ import annotations

from dataclasses import dataclass

from planfgen.brief.programme import RoomType
from planfgen.brief.regulation import RegulationProfile
from planfgen.fabric.axis import WallAxis
from planfgen.fabric.plan import Space

#: Room kinds that need daylight when the programme does not say. The brief's
#: own `RoomSpec.daylight` wins wherever it is available — this is the fallback
#: for a `Space`, which carries a kind but not the line of programme it came from.
DAYLIGHT_KINDS = frozenset(
    {
        RoomType.SEJOUR,
        RoomType.CHAMBRE,
        RoomType.CHAMBRE_PRINCIPALE,
        RoomType.CUISINE,
        RoomType.BUREAU,
    }
)


@dataclass
class Window:
    """One window. `t` is its centre along the wall, `allege` its sill height."""

    wall: WallAxis
    t: float
    width: float
    allege: float
    head: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.t <= 1.0:
            raise ValueError(f"a window sits along its wall, 0..1, not at {self.t}")
        if self.width <= 0:
            raise ValueError(f"width must be positive, got {self.width}")
        if self.head <= self.allege:
            raise ValueError(f"head {self.head} is not above allege {self.allege}")

    @property
    def glazing(self) -> float:
        """Area of glass, in m²."""
        return self.width * (self.head - self.allege)

    @property
    def span(self) -> tuple[float, float]:
        centre = self.t * self.wall.length
        return (centre - self.width / 2, centre + self.width / 2)

    def position(self) -> tuple[float, float]:
        (x0, y0), (x1, y1) = self.wall.p0, self.wall.p1
        return (x0 + self.t * (x1 - x0), y0 + self.t * (y1 - y0))


def needs_daylight(space: Space) -> bool:
    """Whether this space has to see the sky, judged by its kind."""
    return space.kind in DAYLIGHT_KINDS


def required_glazing(space: Space, profile: RegulationProfile) -> float:
    """Glass a room owes its floor: net area times the daylight ratio."""
    return space.surface_utile * profile.daylight_ratio


def size_windows(
    space: Space, exterior_walls: list[WallAxis], profile: RegulationProfile
) -> list[Window]:
    """Spread the room's required glazing across the walls it may open on.

    Wider walls take proportionally more, and every opening keeps a jamb at each
    end. Where the walls cannot carry the whole requirement they carry what they
    can: the shortfall is a fact about the plan for L8 to report, not something
    to be hidden by a window wider than its wall.
    """
    if not exterior_walls:
        return []

    needed = required_glazing(space, profile) / profile.glazing_height
    total = sum(wall.length for wall in exterior_walls)
    if total <= 0 or needed <= 0:
        return []

    windows: list[Window] = []
    for wall in exterior_walls:
        share = needed * wall.length / total
        widest = wall.length - 2 * profile.door_jamb
        width = min(share, widest)
        if width <= 0:
            continue
        windows.append(
            Window(
                wall=wall,
                t=0.5,
                width=width,
                allege=profile.allege_h,
                head=profile.head_h,
            )
        )
    return windows
