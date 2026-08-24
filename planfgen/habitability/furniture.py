"""L7 — the smallest rectangle a room has to contain to be worth building.

**Caveat.** These footprints are *conventional placeholder values*, not verified
Moroccan regulatory or ergonomic requirements, and must not be relied on as
such. Like `brief/regulation.py`, this file exists so that a single table can be
checked and corrected by someone with the current code in hand; nothing else
needs editing if a number here is wrong.

`min_side` is the short dimension, `min_long` the long one, and the test is
against a room's **net** dimensions. Once rooms are axis-aligned rectangles the
largest inscribed rectangle *is* the room, so the check is two float
comparisons — which is what lets it steer the search rather than judge it
afterwards (ARCHITECTURE section 6).
"""

from __future__ import annotations

from dataclasses import dataclass

from planfgen.brief.programme import RoomType


@dataclass(frozen=True)
class FurnitureSpec:
    """The clear rectangle a room's furniture needs, in metres."""

    min_side: float
    min_long: float
    note: str


#: Room types absent from this table carry no furniture requirement. Inventing
#: one here would be an ergonomic rule invented in code.
FURNITURE: dict[RoomType, FurnitureSpec] = {
    RoomType.CHAMBRE_PRINCIPALE: FurnitureSpec(2.70, 3.00, "double bed, two bedsides, wardrobe"),
    RoomType.CHAMBRE: FurnitureSpec(2.40, 2.70, "single or small double, wardrobe"),
    RoomType.SEJOUR: FurnitureSpec(3.00, 4.00, "seating group and a dining table"),
    RoomType.CUISINE: FurnitureSpec(1.80, 2.40, "one run of units plus a passing width"),
    RoomType.SDB: FurnitureSpec(1.70, 1.90, "bath or shower, basin, and a standing zone"),
    RoomType.WC: FurnitureSpec(0.90, 1.40, "pan plus the approach in front of it"),
    RoomType.COULOIR: FurnitureSpec(1.20, 2.00, "clear passing width, and long enough to be a run"),
}
