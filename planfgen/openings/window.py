"""L6 — a window is an interval on a wall, and only where the edge allows one.

CLAUDE.md: openings are legal only where the parcel edge allows. A window on a
`MITOYEN` is not a worse plan, it is a wall through somebody else's building —
which is why the check lives here, on the parcel edge, and not in a score.

How much glass a room needs is `daylight_ratio` of its net floor and never less
than `MIN_GLAZING`; a bay under `MIN_WINDOW_DIMENSION` in any dimension is not a
window (decret 2-64-445 ART. 7). How wide that makes the window follows from the
head and allege heights. All four are regulation values and live in
`brief/regulation.py`, not here.

The arithmetic is plain floats on purpose (`glazing_owed`, `window_capacity`,
`window_widths`): the daylight GATE (`evaluate.constraints.DAYLIGHT_GATE`) runs
it on partition cells inside the search, `search.construct` runs it on regions,
and `size_windows` runs it on the finished wall graph. One rule, three callers,
and they agree because they share it.
"""

from __future__ import annotations

from dataclasses import dataclass

from planfgen.brief.programme import RoomType
from planfgen.brief.regulation import (
    MIN_GLAZING,
    MIN_WINDOW_DIMENSION,
    RegulationProfile,
)
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


def glazing_owed(net_area: float, profile: RegulationProfile) -> float:
    """m2 of glass a room of `net_area` owes: the ratio, and never under 1 m2."""
    return max(net_area * profile.daylight_ratio, MIN_GLAZING)


def width_owed(net_area: float, profile: RegulationProfile) -> float:
    """Metres of window, at the profile's glazing height, that the room owes."""
    return glazing_owed(net_area, profile) / profile.glazing_height


def window_capacity(net_run: float, profile: RegulationProfile) -> float:
    """The widest window a clear run of `net_run` metres of openable facade takes:
    a jamb kept at each end, and nothing at all if what is left, or the glazing
    height, is under `MIN_WINDOW_DIMENSION` — that is not a window."""
    if profile.glazing_height < MIN_WINDOW_DIMENSION - 1e-9:
        return 0.0
    width = net_run - 2 * profile.door_jamb
    return width if width >= MIN_WINDOW_DIMENSION - 1e-9 else 0.0


def window_widths(capacities: list[float], owed: float) -> list[float]:
    """One width per run (0 = no window there) delivering `owed` metres.

    Each window is 0 or between `MIN_WINDOW_DIMENSION` and its run's capacity.
    The fewest, widest runs are used; each gets the minimum and the rest is
    shared in proportion to what each can still take. Where the runs cannot
    carry `owed` they carry all they can. A window may exceed its share to
    reach the minimum: more glass than owed is legal, a 0.20 m slit is not.
    """
    order = sorted(range(len(capacities)), key=lambda i: -capacities[i])
    used: list[int] = []
    total = 0.0
    for i in order:
        if capacities[i] <= 0 or total >= owed - 1e-9:
            break
        used.append(i)
        total += capacities[i]
    widths = [0.0] * len(capacities)
    if not used:
        return widths
    if total <= owed + 1e-9:
        for i in used:
            widths[i] = capacities[i]
        return widths
    rest = max(0.0, owed - MIN_WINDOW_DIMENSION * len(used))
    room = sum(capacities[i] - MIN_WINDOW_DIMENSION for i in used)
    for i in used:
        extra = rest * (capacities[i] - MIN_WINDOW_DIMENSION) / room if room > 0 else 0.0
        widths[i] = MIN_WINDOW_DIMENSION + extra
    return widths


def required_glazing(space: Space, profile: RegulationProfile) -> float:
    """Glass a room owes its floor: net area times the daylight ratio, and
    never under `MIN_GLAZING` (decret ART. 7)."""
    return glazing_owed(space.surface_utile, profile)


def net_run(wall: WallAxis, space: Space) -> float:
    """Metres of `wall` that face the room's clear floor: the wall's run
    clipped to the net polygon, so the half-walls at each corner are off it."""
    minx, miny, maxx, maxy = space.net_polygon.bounds
    axis = 0 if wall.is_horizontal else 1
    lo, hi = sorted((wall.p0[axis], wall.p1[axis]))
    net_lo, net_hi = (minx, maxx) if axis == 0 else (miny, maxy)
    return max(0.0, min(hi, net_hi) - max(lo, net_lo))


def size_windows(
    space: Space, exterior_walls: list[WallAxis], profile: RegulationProfile
) -> list[Window]:
    """Windows delivering the room's required glazing on the walls it may open on.

    Each window is centred on the clear stretch of its wall, keeps a jamb at
    each end, and is at least `MIN_WINDOW_DIMENSION` wide (`window_widths`).
    Where the walls cannot carry the whole requirement they carry what they
    can: the shortfall is a fact about the plan for L6 to report, not something
    to be hidden by a window wider than its wall.
    """
    if not exterior_walls:
        return []
    owed = required_glazing(space, profile) / profile.glazing_height
    runs = [net_run(wall, space) for wall in exterior_walls]
    widths = window_widths([window_capacity(r, profile) for r in runs], owed)

    minx, miny, maxx, maxy = space.net_polygon.bounds
    windows: list[Window] = []
    for wall, width in zip(exterior_walls, widths):
        if width <= 0:
            continue
        axis = 0 if wall.is_horizontal else 1
        lo, hi = sorted((wall.p0[axis], wall.p1[axis]))
        net_lo, net_hi = (minx, maxx) if axis == 0 else (miny, maxy)
        centre = (max(lo, net_lo) + min(hi, net_hi)) / 2
        windows.append(
            Window(
                wall=wall,
                t=(centre - wall.p0[axis]) / wall.length,
                width=width,
                allege=profile.allege_h,
                head=profile.head_h,
            )
        )
    return windows
