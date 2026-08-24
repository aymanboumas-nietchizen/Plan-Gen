"""L0 — the programme: which rooms are wanted, of what kind, and how big.

`surface_utile` is always the **net** area of a room — the polygon left after
every bounding wall has taken its half-thickness. Nothing in this module knows
about walls; it only records the target the later layers must hit exactly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class RoomType(Enum):
    """The kinds of room a residential programme can ask for."""

    SEJOUR = "sejour"
    CHAMBRE = "chambre"
    CHAMBRE_PRINCIPALE = "chambre_principale"
    CUISINE = "cuisine"
    SDB = "sdb"
    WC = "wc"
    COULOIR = "couloir"
    ENTREE = "entree"
    BUREAU = "bureau"
    CELLIER = "cellier"
    TERRASSE = "terrasse"

    @property
    def is_wet(self) -> bool:
        """True for rooms that need a plumbing shaft (L4 groups these on stacks)."""
        return self in _WET

    @property
    def is_circulation(self) -> bool:
        """True for rooms that are a width rather than an area (see CLAUDE.md).

        Circulation area is an *output* of the partition, never an input, so
        L2 gives these a clear width and lets their area fall out of the plan.
        """
        return self in _CIRCULATION


_WET = frozenset({RoomType.CUISINE, RoomType.SDB, RoomType.WC})
_CIRCULATION = frozenset({RoomType.COULOIR, RoomType.ENTREE})


class Orientation(Enum):
    """Compass sector, in French initials. Values index the 8 sectors clockwise
    from north so that `Orientation(round(bearing / (pi/4)) % 8)` is the sector.
    """

    N = 0
    NE = 1
    E = 2
    SE = 3
    S = 4
    SO = 5
    O = 6
    NO = 7


#: Half-width of one compass sector, in radians. A bearing within this of a
#: sector centre belongs to that sector.
SECTOR = math.pi / 4


@dataclass(frozen=True)
class RoomSpec:
    """One line of the programme."""

    nom: str
    kind: RoomType
    surface_utile: float
    couleur: str
    daylight: bool = True
    orientation_pref: Orientation | None = None

    @classmethod
    def from_json(cls, entry: dict) -> RoomSpec:
        """Build one room from a v2 brief entry.

        Expects the v2 field names — `nom`, `kind`, `surface_utile`, `couleur`,
        and optionally `daylight` and `orientation_pref`. `kind` and
        `orientation_pref` are the enum *member names* ("CHAMBRE", "SE").
        """
        pref = entry.get("orientation_pref")
        return cls(
            nom=entry["nom"],
            kind=RoomType[entry["kind"]],
            surface_utile=float(entry["surface_utile"]),
            couleur=entry["couleur"],
            daylight=bool(entry.get("daylight", True)),
            orientation_pref=Orientation[pref] if pref else None,
        )


@dataclass(frozen=True)
class Programme:
    """Everything the client asked for, before any geometry exists."""

    rooms: list[RoomSpec]

    @property
    def total_utile(self) -> float:
        """Sum of the net areas requested, in m²."""
        return sum(r.surface_utile for r in self.rooms)

    def by_nom(self, nom: str) -> RoomSpec:
        """The room with this exact `nom`. Raises KeyError if there is none."""
        for room in self.rooms:
            if room.nom == nom:
                return room
        raise KeyError(f"no room named {nom!r} in the programme")

    @property
    def circulation_rooms(self) -> list[RoomSpec]:
        """The rooms whose area is an output rather than an input."""
        return [r for r in self.rooms if r.kind.is_circulation]

    @classmethod
    def from_json(cls, data: dict) -> Programme:
        """Build the programme from a whole brief document's `programme` list."""
        return cls(rooms=[RoomSpec.from_json(e) for e in data["programme"]])
