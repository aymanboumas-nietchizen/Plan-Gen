"""Studio — typologies an architect starts from, instead of an empty table.

Each preset is a programme, the relations that go with it, and a lot it fits.
Areas are ordinary Moroccan agency figures, not numbers calibrated to fill one
parcel: since the studio sizes the footprint with `fit_brief`, the lot only has
to be large enough, not exactly right.

WHAT IS MISSING, AND WHY (measured 2026-09-28 through `pipeline.generate`, four
seeds on each profile):

- **No separate WC.** A 2 m2 WC is furnishable only on a corridor side at most
  2.2 m deep, bedrooms need 2.4-2.7 m, and every room on one side of a single
  corridor shares its depth. F3 with a WC: 0 of 4 on every profile; with an
  entree as well, 2, 0 and 1 of 4 (the WC can open off the hall). The presets
  fold the WC into the SDB until the engine has a dégagement to hang it on.
- **No F2.** 1 of 4 on the placeholder profile, none on the sourced ones.

The ENTREE is back since 2026-09-28: it used to name the corridor band, and
now it is a hall (`RoomType.names_band`). F3 and F4 with one: 4 of 4 on every
profile. Every preset below generates on all three profiles, and
`test_studio.py` holds it to that.
"""

from __future__ import annotations

from dataclasses import dataclass

#: One row of the programme table: nom, kind, surface_utile, orientation.
Room = tuple[str, str, float, str]
#: One row of the relations table: a, b, kind, weight.
Link = tuple[str, str, str, float]


@dataclass(frozen=True)
class Preset:
    """A starting point: what to build, how it connects, and a lot it fits."""

    label: str
    rooms: tuple[Room, ...]
    relations: tuple[Link, ...]
    width: float
    depth: float


def _flat(rooms: tuple[Room, ...]) -> tuple[Link, ...]:
    """Night rooms off the corridor, day rooms together, the bathroom kept
    away from the living room."""
    noms = {nom: kind for nom, kind, _, _ in rooms}
    links: list[Link] = [
        ("Couloir", nom, "CONNECTED", 2.0)
        for nom, kind in noms.items()
        if kind in ("CHAMBRE", "CHAMBRE_PRINCIPALE", "SDB")
    ]
    links += [
        ("Entree", "Sejour", "CONNECTED", 2.0),
        ("Entree", "Couloir", "CONNECTED", 2.0),
        ("Sejour", "Cuisine", "CONNECTED", 1.5),
        ("Cuisine", "SDB", "ADJACENT", 1.0),
        ("SDB", "Sejour", "SEPARATED", 1.0),
    ]
    return tuple(links)


_F3: tuple[Room, ...] = (
    ("Entree", "ENTREE", 5.0, ""),
    ("Sejour", "SEJOUR", 24.0, "S"),
    ("Cuisine", "CUISINE", 9.0, "N"),
    ("Ch1", "CHAMBRE_PRINCIPALE", 13.0, "S"),
    ("Ch2", "CHAMBRE", 11.0, "E"),
    ("SDB", "SDB", 7.0, ""),
    ("Couloir", "COULOIR", 6.0, ""),
)

_F4: tuple[Room, ...] = (
    ("Entree", "ENTREE", 5.0, ""),
    ("Sejour", "SEJOUR", 30.0, "S"),
    ("Cuisine", "CUISINE", 11.0, "N"),
    ("Ch1", "CHAMBRE_PRINCIPALE", 14.0, "S"),
    ("Ch2", "CHAMBRE", 12.0, "E"),
    ("Ch3", "CHAMBRE", 11.0, "O"),
    ("SDB", "SDB", 7.0, ""),
    ("Couloir", "COULOIR", 9.0, ""),
)

_DEMO: tuple[Room, ...] = (
    ("Sejour", "SEJOUR", 33.8, "S"),
    ("Cuisine", "CUISINE", 13.5, "N"),
    ("Ch1", "CHAMBRE_PRINCIPALE", 19.2, "N"),
    ("Ch2", "CHAMBRE", 15.8, "S"),
    ("SDB", "SDB", 10.2, "E"),
    ("Couloir", "COULOIR", 8.0, ""),
)

_DEMO_RELATIONS: tuple[Link, ...] = (
    ("Couloir", "Sejour", "CONNECTED", 2.0),
    ("Couloir", "Ch1", "CONNECTED", 2.0),
    ("Couloir", "Ch2", "CONNECTED", 2.0),
    ("Couloir", "SDB", "CONNECTED", 1.0),
    ("Sejour", "Cuisine", "CONNECTED", 1.5),
    ("Cuisine", "SDB", "ADJACENT", 2.0),
    ("SDB", "Sejour", "SEPARATED", 1.0),
)

#: In the order the selector shows them. The first is the default.
PRESETS: dict[str, Preset] = {
    "F3": Preset("F3 — 75 m2", _F3, _flat(_F3), 9.0, 11.0),
    "F4": Preset("F4 — 99 m2", _F4, _flat(_F4), 11.0, 13.0),
    "DEMO": Preset("Demo — 12 x 10 m", _DEMO, _DEMO_RELATIONS, 12.0, 10.0),
}
