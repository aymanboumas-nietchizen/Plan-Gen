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

#: Interior door LEAF widths by the kind of room the door serves, in m — the
#: agency's "portes de 73 / 83 / 93". **Agency practice supplied by the user
#: (the architect) on 2026-09-29, not a sourced regulation.** Kinds absent here
#: keep the profile's `door_leaf` and `door_jamb`, i.e. today's `door_module`.
_DOOR_LEAF_BY_KIND: dict[RoomType, float] = {
    RoomType.SDB: 0.73,
    RoomType.WC: 0.73,
    RoomType.CUISINE: 0.83,
    RoomType.CHAMBRE: 0.93,
    RoomType.CHAMBRE_PRINCIPALE: 0.93,
    RoomType.BUREAU: 0.93,
    RoomType.SEJOUR: 0.93,
    # The laundry takes the wet rooms' neighbour size: 0.83 leaf, 0.93 module.
    # The user's decision of 2026-09-29, with the rename CELLIER -> BUANDERIE.
    RoomType.BUANDERIE: 0.83,
    # The hall keeps the opening it had as an unlisted kind — door_leaf 0.80 +
    # 2 x door_jamb 0.10 = a 1.00 m module — written down as a decision rather
    # than a fallback: 0.90 leaf + 2 x door_frame 0.05 = 1.00. The user's
    # decision of 2026-09-29. (The FRONT door is `entry_leaf`, unchanged.)
    RoomType.ENTREE: 0.90,
}


@dataclass(frozen=True)
class RegulationProfile:
    """Every dimensional constant the layers are allowed to consult.

    Room types absent from `min_area` or `min_width` simply carry no minimum —
    v1 stated none for them, and inventing one here would be a regulation
    invented in code.

    `coverage_max` is the CES, the emprise au sol: built area over parcel area.
    It is 1.0 in every profile below, including the two sourced ones, and that
    is not an oversight. **Neither the décret nor the Casablanca arrêté states a
    CES.** Both are building-form texts — gabarit, alignement, saillies, hauteur
    — and the coverage ratio comes from the zone's plan d'aménagement, which is
    a per-project document rather than a national rule. So it is a value the
    caller supplies, and 1.0 means "unconstrained until someone does".
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
    coverage_max: float = 1.0
    min_area: dict[RoomType, float] = field(default_factory=lambda: dict(_MIN_AREA))
    min_width: dict[RoomType, float] = field(default_factory=lambda: dict(_MIN_WIDTH))
    #: Per-kind interior leaves (see `_DOOR_LEAF_BY_KIND`) and the frame — the
    #: huisserie — each side of one: 0.05 m, also agency practice (2026-09-29).
    #: Not `door_jamb`, which still sizes the front door and window margins.
    door_leaf_by_kind: dict[RoomType, float] = field(
        default_factory=lambda: dict(_DOOR_LEAF_BY_KIND)
    )
    door_frame: float = 0.05

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

    def door_leaf_for(self, kind: RoomType) -> float:
        """The leaf of the door into a room of this kind."""
        return self.door_leaf_by_kind.get(kind, self.door_leaf)

    def door_frame_for(self, kind: RoomType) -> float:
        """What stands each side of that leaf: the frame for a per-kind leaf,
        else the profile's jamb, so an unlisted kind keeps `door_module`."""
        return self.door_frame if kind in self.door_leaf_by_kind else self.door_jamb

    def door_module_for(self, kind: RoomType) -> float:
        """Metres of shared wall the door into a room of this kind needs:
        0.83 for a WC or SDB, 0.93 for a kitchen or buanderie, 1.00 for the
        entree, 1.03 for a bedroom, bureau or sejour; `door_module` for any
        kind without a leaf of its own."""
        return self.door_leaf_for(kind) + 2 * self.door_frame_for(kind)


_WALL_ATTR = {
    "facade": "facade_t",
    "porteur": "porteur_t",
    "cloison": "cloison_t",
    "wet": "wet_t",
}


#: The default profile. Placeholder values — see the module docstring.
MA_PROFILE = RegulationProfile()


# ---------------------------------------------------------------------------
# Sourced profiles. Everything above this line is unsourced placeholder; these
# two carry figures read off the regulations themselves, with the article that
# states each one. They disagree with each other, which is the reason a profile
# is a profile: a plan legal in an habitat economique zone is not necessarily
# legal in Casablanca, and one global constant cannot express that.
# ---------------------------------------------------------------------------

#: Decret n° 2-64-445 (26 December 1964), Reglement general de construction
#: d'habitat economique. Applies to `zones d'habitat economique`.
#:   ART. 3  ceiling 2.60 m coastal (within 25 km), 2.80 m inland, 2.25 m service
#:   ART. 4  smallest dimension of a habitable room 2.35 m; 2.20 m if that is an
#:           average width; and if a room is lit only on its short side its length
#:           is at most twice the height under the lintel of its highest window
#:   ART. 5  piece principale 12 m2; other habitable rooms 9 m2; cuisine 5 m2
#:           (4 m2 if linked to a court or loggia of 2 m2), no kitchen dimension
#:           under 1.70 m; salle d'eau 1.30 m2; WC 0.85 m2
#:   ART. 6  stairs and degagements 0.80 m for one dwelling per floor, 1.00 m for
#:           two to four, 1.10 m for five to ten, 1.20 m above ten
#:   ART. 7  a bay under 0.35 m in any dimension is not a window; every habitable
#:           room and kitchen is lit to at least 1/10 of its floor and never less
#:           than 1 m2
MA_ECONOMIQUE = RegulationProfile(
    corridor_clear=0.80,
    daylight_ratio=0.10,
    min_area={
        RoomType.SEJOUR: 12.0,
        RoomType.CHAMBRE_PRINCIPALE: 12.0,
        RoomType.CHAMBRE: 9.0,
        RoomType.BUREAU: 9.0,
        RoomType.CUISINE: 5.0,
        RoomType.SDB: 1.30,
        RoomType.WC: 0.85,
    },
    min_width={
        RoomType.SEJOUR: 2.35,
        RoomType.CHAMBRE_PRINCIPALE: 2.35,
        RoomType.CHAMBRE: 2.35,
        RoomType.BUREAU: 2.35,
        RoomType.CUISINE: 1.70,
        RoomType.COULOIR: 0.80,
    },
)

#: Arrete municipal permanent, Casablanca. Municipal, and stricter than the
#: national decree on almost everything.
#:   ART. 63  any permanent habitation 9 m2 with a window opening directly to
#:            open air of at least 1/6 of the room; salles communes / living
#:            14 m2; cuisines 6 m2, glazed opening at least 1 m2, and at least
#:            4 m of direct view
#:   ART. 64  a debarras may not exceed 1.75 m in width
#:   ART. 65  salles de bains at least 3 m2
MA_CASABLANCA = RegulationProfile(
    corridor_clear=0.90,
    daylight_ratio=1.0 / 6.0,
    min_area={
        RoomType.SEJOUR: 14.0,
        RoomType.CHAMBRE_PRINCIPALE: 9.0,
        RoomType.CHAMBRE: 9.0,
        RoomType.BUREAU: 9.0,
        RoomType.CUISINE: 6.0,
        RoomType.SDB: 3.0,
        RoomType.WC: 0.85,
    },
    min_width={
        RoomType.SEJOUR: 2.35,
        RoomType.CHAMBRE_PRINCIPALE: 2.35,
        RoomType.CHAMBRE: 2.35,
        RoomType.BUREAU: 2.35,
        RoomType.CUISINE: 1.70,
        RoomType.COULOIR: 0.90,
    },
)

#: Minimum glazing per room whatever the ratio gives — decret ART. 7, and the
#: same figure in Casablanca ART. 63 for kitchens.
MIN_GLAZING = 1.00

#: A bay smaller than this in any dimension is not a window — decret ART. 7.
MIN_WINDOW_DIMENSION = 0.35

PROFILES = {
    "placeholder": MA_PROFILE,
    "economique": MA_ECONOMIQUE,
    "casablanca": MA_CASABLANCA,
}
