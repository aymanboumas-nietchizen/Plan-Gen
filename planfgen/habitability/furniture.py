"""L7 — the smallest rectangle a room has to contain to be worth building.

**Caveat.** These footprints are *conventional placeholder values*, not verified
Moroccan regulatory or ergonomic requirements, and must not be relied on as
such. Like `brief/regulation.py`, this file exists so that a single table can be
checked and corrected by someone with the current code in hand; nothing else
needs editing if a number here is wrong.

`min_side` is the short dimension and `min_long` the long one, tested against a
room's **net** dimensions. Once rooms are axis-aligned rectangles the largest
inscribed rectangle *is* the room, so the check is a handful of float
comparisons — which is what lets it steer the search rather than judge it
afterwards (ARCHITECTURE section 6).

`max_ratio` closes a hole those two numbers leave open. A minimum footprint has
a floor but no ceiling: a WC measured 5.17 x 0.92 satisfies 0.90 x 1.40 twice
over and is a corridor with a pan at one end. The furniture does not merely have
to fit inside the room, it has to be *arrangeable* in it, and past some
proportion it is not. `None` means unbounded, which is right for a corridor and
wrong for everything else.

This is a furniture constraint, not the aspect rule S9b took out of the gates.
CLAUDE.md lists compactness among the scored judgement calls and furniture fit
among the gates; asking whether a bed can be arranged in a room is the second
question, not the first.
"""

from __future__ import annotations

from dataclasses import dataclass

from planfgen.brief.programme import RoomType


@dataclass(frozen=True)
class FurnitureSpec:
    """The clear rectangle a room's furniture needs, and how far from square it
    may be and still be arrangeable. `max_ratio` of `None` is unbounded."""

    min_side: float
    min_long: float
    note: str
    max_ratio: float | None = None


#: Room types absent from this table carry no furniture requirement. Inventing
#: one here would be an ergonomic rule invented in code.
FURNITURE: dict[RoomType, FurnitureSpec] = {
    RoomType.CHAMBRE_PRINCIPALE: FurnitureSpec(
        2.70, 3.00, "double bed, two bedsides, wardrobe", max_ratio=2.0),
    RoomType.CHAMBRE: FurnitureSpec(
        2.40, 2.70, "single or small double, wardrobe", max_ratio=2.0),
    RoomType.SEJOUR: FurnitureSpec(
        3.00, 4.00, "seating group and a dining table", max_ratio=2.2),
    RoomType.CUISINE: FurnitureSpec(
        1.80, 2.40, "one run of units plus a passing width", max_ratio=2.5),
    RoomType.SDB: FurnitureSpec(
        1.70, 1.90, "bath or shower, basin, and a standing zone", max_ratio=2.2),
    RoomType.WC: FurnitureSpec(
        0.90, 1.40, "pan plus the approach in front of it", max_ratio=2.2),
    RoomType.CELLIER: FurnitureSpec(
        1.20, 1.60, "shelving one side and room to stand", max_ratio=2.5),
    RoomType.BUREAU: FurnitureSpec(
        2.10, 2.60, "desk, chair pulled back, and shelving", max_ratio=2.2),
    RoomType.ENTREE: FurnitureSpec(
        1.40, 1.60, "somewhere to put a coat and turn round", max_ratio=2.5),
    # A corridor is meant to be long, so it alone has no ceiling.
    RoomType.COULOIR: FurnitureSpec(
        1.20, 2.00, "clear passing width, and long enough to be a run"),
}
