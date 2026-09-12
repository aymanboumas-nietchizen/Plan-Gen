"""L0 — the parcel: an outline whose every edge is typed and oriented.

The v1 `Envelope` was a bare width and height. A plan cannot be generated from
that, because whether a wall may carry a window is a property of the *edge* it
sits on, not of the room behind it. So every segment of the outline gets an
`EdgeType`, the parcel knows where north is, and one edge is the entry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from shapely.geometry import LineString, Polygon

from planfgen.brief.programme import SECTOR, Orientation

#: Shapely's mitre join, so eroding a rectangle keeps square corners.
_MITRE = 2


class EdgeType(Enum):
    """What lies on the far side of one segment of the outline."""

    STREET = "street"
    COURT = "court"
    GARDEN = "garden"
    MITOYEN = "mitoyen"
    RETRAIT = "retrait"

    @property
    def openable(self) -> bool:
        """True if a wall on this edge may carry a window.

        A `MITOYEN` edge is a party wall shared with the neighbour and a
        `RETRAIT` edge is a mandated setback; neither may be pierced.
        """
        return self not in _BLIND


_BLIND = frozenset({EdgeType.MITOYEN, EdgeType.RETRAIT})


@dataclass(frozen=True)
class EdgeSpec:
    """One typed segment of the outline. `index` is its position in the ring.

    `setback` is how far, in metres, the building must stand back from this
    boundary. It lives on the edge rather than on the regulation profile
    because it varies boundary by boundary — a plot is set back from the street
    by one distance, from a neighbour by another, and built up to a party wall
    with none at all. There is no national figure to put in a profile: the
    decree's only stated retrait (ART. 46, 2 m) governs terrace superstructures,
    not the footprint.
    """

    index: int
    kind: EdgeType
    setback: float = 0.0

    def __post_init__(self) -> None:
        if self.setback < 0:
            raise ValueError(f"a setback cannot be negative, got {self.setback}")

    @classmethod
    def from_json(cls, entry: dict) -> EdgeSpec:
        return cls(
            index=int(entry["index"]),
            kind=EdgeType[entry["kind"]],
            setback=float(entry.get("setback", 0.0)),
        )


@dataclass(frozen=True)
class Parcel:
    """The buildable outline, with its edges typed and its north known.

    `edges[i]` describes `segment(i)`, so the list is stored in ring order and
    validated as such — a mismatch would otherwise mistype windows silently.
    """

    outline: Polygon
    edges: list[EdgeSpec]
    north: float
    entry_edge: int

    def __post_init__(self) -> None:
        n = self.n_segments
        if len(self.edges) != n:
            raise ValueError(
                f"parcel has {n} outline segments but {len(self.edges)} edge specs"
            )
        actual = [e.index for e in self.edges]
        if actual != list(range(n)):
            raise ValueError(
                f"edges must be given in ring order with indices 0..{n - 1}, got {actual}"
            )
        if not 0 <= self.entry_edge < n:
            raise ValueError(
                f"entry_edge {self.entry_edge} is outside the range 0..{n - 1}"
            )
        entry_kind = self.edges[self.entry_edge].kind
        if entry_kind not in _ENTRY_KINDS:
            raise ValueError(
                f"entry_edge {self.entry_edge} is {entry_kind.name}; the entry must be "
                f"on a STREET or GARDEN edge"
            )

    @property
    def n_segments(self) -> int:
        """Number of segments in the outline ring."""
        return len(self.outline.exterior.coords) - 1

    def segment(self, i: int) -> LineString:
        """Segment `i` of the outline, in ring order."""
        coords = list(self.outline.exterior.coords)
        return LineString([coords[i], coords[i + 1]])

    def openable(self, i: int) -> bool:
        """True if segment `i` may carry a window."""
        return self.edges[i].kind.openable

    def orientation_of(self, i: int) -> Orientation:
        """The compass sector segment `i` faces, as its outward normal.

        Bearings run clockwise from north, which is `atan2(x, y)` in the local
        frame; `north` is where true north lies in that same frame, so it is
        simply subtracted. The ring may be wound either way, so the normal is
        flipped to stay outward rather than reordering the caller's edges.
        """
        (x0, y0), (x1, y1) = self.segment(i).coords
        dx, dy = x1 - x0, y1 - y0
        sign = 1.0 if self.outline.exterior.is_ccw else -1.0
        nx, ny = sign * dy, -sign * dx
        bearing = (math.atan2(nx, ny) - self.north) % (2 * math.pi)
        return Orientation(int(round(bearing / SECTOR)) % 8)

    def side_of(self, i: int) -> str:
        """Which side of the bounding box segment `i` lies on.

        One of "left", "right", "bottom", "top", read from the segment's
        midpoint. Bounding-box arithmetic, which is exact for the rectangular
        parcels the engine builds on today; a rectilinear parcel has edges that
        are on no side of its bounding box at all, and placing a building on one
        is S16's problem.
        """
        minx, miny, maxx, maxy = self.outline.bounds
        (x0, y0), (x1, y1) = self.segment(i).coords
        mid_x, mid_y = (x0 + x1) / 2, (y0 + y1) / 2
        return min(
            (
                (abs(mid_x - minx), "left"),
                (abs(mid_x - maxx), "right"),
                (abs(mid_y - miny), "bottom"),
                (abs(mid_y - maxy), "top"),
            )
        )[1]

    def sides(self) -> dict[str, EdgeSpec]:
        """The edge governing each side of the bounding box.

        Where two edges fall on the same side — which a rectilinear outline
        does — the one demanding the larger setback wins, since both have to be
        honoured.
        """
        out: dict[str, EdgeSpec] = {}
        for spec in self.edges:
            side = self.side_of(spec.index)
            if side not in out or spec.setback > out[side].setback:
                out[side] = spec
        return out

    def buildable_bounds(self) -> tuple[float, float, float, float]:
        """(minx, miny, maxx, maxy) of what may be built on, after setbacks.

        Raises if the setbacks leave nothing.
        """
        minx, miny, maxx, maxy = self.outline.bounds
        sides = self.sides()

        def back(side: str) -> float:
            spec = sides.get(side)
            return spec.setback if spec else 0.0

        box = (
            minx + back("left"),
            miny + back("bottom"),
            maxx - back("right"),
            maxy - back("top"),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError(
                f"the setbacks leave nothing to build on: a "
                f"{maxx - minx:.2f} x {maxy - miny:.2f} m parcel reduced to "
                f"{box[2] - box[0]:.2f} x {box[3] - box[1]:.2f} m"
            )
        return box

    def interior(self, facade_t: float) -> Polygon:
        """The outline eroded by the façade thickness — the buildable inside."""
        return self.outline.buffer(-facade_t, join_style=_MITRE)

    @classmethod
    def from_json(cls, data: dict) -> Parcel:
        """Build the parcel from a whole brief document's `parcel` object."""
        spec = data["parcel"]
        return cls(
            outline=Polygon([tuple(pt) for pt in spec["outline"]]),
            edges=[EdgeSpec.from_json(e) for e in spec["edges"]],
            north=float(spec["north"]),
            entry_edge=int(spec["entry_edge"]),
        )


_ENTRY_KINDS = frozenset({EdgeType.STREET, EdgeType.GARDEN})
