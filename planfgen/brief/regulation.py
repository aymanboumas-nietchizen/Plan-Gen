"""L0 — the regulation profile: every dimensional rule, as data in one place.

**Caveat.** The wall thicknesses, door widths, clear corridor width, PMR turning
circle, daylight ratio and the minimum areas and widths below are *conventional
placeholder values* drawn from the v1 engine's `rules/ma_rules.py` and from
common practice — they are **not** verified Moroccan regulatory requirements and
must not be relied on as such. They live here, as data rather than as literals
scattered through the layers, precisely so that this single file is the only
thing someone with the current code in hand has to check and correct. If a
number in this file is wrong, nothing else needs editing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from planfgen.brief.programme import RoomType

#: Minimum net areas in m², from the v1 hard rules in `rules/ma_rules.py`.
#: v1 matched room types by substring, so its "chambre" rule also covered
#: "chambre principale"; here the two are separate keys with the v1 values.
_MIN_AREA: dict[RoomType, float] = {
    RoomType.CHAMBRE_PRINCIPALE: 12.0,
    RoomType.CHAMBRE: 9.0,
    RoomType.CUISINE: 6.0,
    RoomType.SDB: 3.5,
    RoomType.WC: 1.2,
}

#: Minimum net widths in m, from the v1 soft rules in `rules/ma_rules.py`.
#: `COULOIR` comes from v1's `MinCorridorWidthRule`, and `CHAMBRE_PRINCIPALE`
#: from the "chambre" rule that matched it by substring.
_MIN_WIDTH: dict[RoomType, float] = {
    RoomType.SEJOUR: 3.00,
    RoomType.CHAMBRE: 2.70,
    RoomType.CHAMBRE_PRINCIPALE: 2.70,
    RoomType.CUISINE: 1.80,
    RoomType.SDB: 1.70,
    RoomType.WC: 1.20,
    RoomType.COULOIR: 1.20,
}


@dataclass(frozen=True)
class RegulationProfile:
    """Every dimensional constant the layers are allowed to consult.

    Room types absent from `min_area` or `min_width` simply carry no minimum —
    v1 stated none for them, and inventing one here would be a regulation
    invented in code.
    """

    facade_t: float = 0.30
    porteur_t: float = 0.20
    cloison_t: float = 0.10
    wet_t: float = 0.20
    corridor_clear: float = 1.20
    door_leaf: float = 0.80
    entry_leaf: float = 0.90
    door_jamb: float = 0.10
    pmr_circle: float = 1.50
    daylight_ratio: float = 0.125
    allege_h: float = 1.00
    head_h: float = 2.20
    min_area: dict[RoomType, float] = field(default_factory=lambda: dict(_MIN_AREA))
    min_width: dict[RoomType, float] = field(default_factory=lambda: dict(_MIN_WIDTH))

    @property
    def glazing_height(self) -> float:
        """Head less allege: how tall a window is, and so how wide it must be
        to deliver the glazing a room needs."""
        return self.head_h - self.allege_h

    def thickness_of(self, wall_kind: str) -> float:
        """Thickness in m of a wall of this kind.

        One of "facade", "porteur", "cloison" or "wet".
        """
        try:
            return getattr(self, _WALL_ATTR[wall_kind])
        except KeyError:
            raise ValueError(
                f"unknown wall kind {wall_kind!r}; expected one of "
                f"{', '.join(sorted(_WALL_ATTR))}"
            ) from None

    @property
    def entry_module(self) -> float:
        """Metres of facade the front door needs: a wider leaf, same jambs."""
        return self.entry_leaf + 2 * self.door_jamb

    @property
    def door_module(self) -> float:
        """Metres of shared wall a door needs: one leaf plus a jamb each side.

        This is the length that makes an adjacency *door-capable*. Two rooms
        touching over less than this are not connectable, however long the
        contact looks in a tolerance test.
        """
        return self.door_leaf + 2 * self.door_jamb


_WALL_ATTR = {
    "facade": "facade_t",
    "porteur": "porteur_t",
    "cloison": "cloison_t",
    "wet": "wet_t",
}


#: The default profile. Placeholder values — see the module docstring.
MA_PROFILE = RegulationProfile()
