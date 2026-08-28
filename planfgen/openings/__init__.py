"""L6 — `openings/`: doors that swing free, windows only where the edge allows.

An opening is an interval hosted on a wall. Both rules here are refusals: a door
needs `door_module` metres of shared run, and a window needs an edge the parcel
says may be pierced. What could not be placed is named in `OpeningReport.errors`.
"""

from planfgen.openings.door import ENTRY_LEAF, Door, free_slot
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
    needs_daylight,
    required_glazing,
    size_windows,
)

__all__ = [
    "DAYLIGHT_KINDS",
    "ENTRY_LEAF",
    "Door",
    "OpeningReport",
    "Window",
    "free_slot",
    "needs_daylight",
    "openable_walls",
    "place_doors",
    "place_openings",
    "place_windows",
    "required_glazing",
    "size_windows",
]
