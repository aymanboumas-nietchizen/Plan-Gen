"""L6 — `openings/`: doors that swing free, windows only where the edge allows.

An opening is an interval hosted on a wall. Both rules here are refusals: a door
needs `door_module` metres of shared run, and a window needs an edge the parcel
says may be pierced. Where two circulation spaces meet, the opening is a
`Passage` — no leaf, no swing — over `junction_module`. What could not be placed is named in `OpeningReport.errors`.
"""

from planfgen.openings.door import ENTRY_LEAF, Door, Passage, free_slot
from planfgen.openings.place import (
    OpeningReport,
    openable_walls,
    place_doors,
    place_openings,
    place_windows,
)
from planfgen.openings.window import (
    DAYLIGHT_KINDS,
    Window,
    glazing_owed,
    needs_daylight,
    required_glazing,
    size_windows,
    width_owed,
    window_capacity,
    window_widths,
)

__all__ = [
    "DAYLIGHT_KINDS",
    "ENTRY_LEAF",
    "Door",
    "OpeningReport",
    "Passage",
    "Window",
    "free_slot",
    "glazing_owed",
    "needs_daylight",
    "openable_walls",
    "place_doors",
    "place_openings",
    "place_windows",
    "required_glazing",
    "size_windows",
    "width_owed",
    "window_capacity",
    "window_widths",
]
