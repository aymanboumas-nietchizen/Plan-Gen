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
proportion it is not.

The figure is 3.0 and it was chosen by measurement, not taste. Decret 2-64-445
imposes no aspect ceiling at all — only a smallest dimension of 2.35 m for a
habitable room (ART. 4) — so this number is ours and it costs capacity. Swept
against a growing programme, the ceiling on how many rooms the search can place
went: unbounded 11, at 4.0 ten, at 3.5 and 3.0 eight, at 2.5 six. The first
values tried here were 2.0 to 2.5 per room type, and they cost five rooms of
capacity to catch a fault that 3.0 catches too — the WC above is 5.62:1 and the
cellier beside it 3.21:1, and both are refused at 3.0.

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


#: How far from square a room may be and still be arrangeable. One figure for
#: every type, because there is no evidence for making it vary by room and a
#: table of nine invented numbers reads as though there were. See the module
#: docstring for how 3.0 was arrived at.
ARRANGEABLE = 3.0

#: Room types absent from this table carry no furniture requirement. Inventing
#: one here would be an ergonomic rule invented in code.
FURNITURE: dict[RoomType, FurnitureSpec] = {
    RoomType.CHAMBRE_PRINCIPALE: FurnitureSpec(
        2.70, 3.00, "double bed, two bedsides, wardrobe", max_ratio=ARRANGEABLE),
    RoomType.CHAMBRE: FurnitureSpec(
        2.40, 2.70, "single or small double, wardrobe", max_ratio=ARRANGEABLE),
    RoomType.SEJOUR: FurnitureSpec(
        3.00, 4.00, "seating group and a dining table", max_ratio=ARRANGEABLE),
    RoomType.CUISINE: FurnitureSpec(
        1.80, 2.40, "one run of units plus a passing width", max_ratio=ARRANGEABLE),
    RoomType.SDB: FurnitureSpec(
        1.70, 1.90, "bath or shower, basin, and a standing zone", max_ratio=ARRANGEABLE),
    RoomType.WC: FurnitureSpec(
        0.90, 1.40, "pan plus the approach in front of it", max_ratio=ARRANGEABLE),
    RoomType.CELLIER: FurnitureSpec(
        1.20, 1.60, "shelving one side and room to stand", max_ratio=ARRANGEABLE),
    RoomType.BUREAU: FurnitureSpec(
        2.10, 2.60, "desk, chair pulled back, and shelving", max_ratio=ARRANGEABLE),
    RoomType.ENTREE: FurnitureSpec(
        1.40, 1.60, "somewhere to put a coat and turn round", max_ratio=ARRANGEABLE),
}

# COULOIR is deliberately absent. A corridor's clear width is a REGULATION
# value, and CLAUDE.md keeps those in `brief/regulation.py` and nowhere else —
# it is `profile.corridor_clear`, and the band cut sets the corridor to exactly
# that by construction, so there is nothing left for a gate to check.
#
# Having it here as well was a duplicated regulation, and it duly went wrong the
# moment a real profile arrived: decret 2-64-445 ART. 6 puts a degagement
# serving one dwelling at 0.80 m, and a 0.80 m corridor failed a 1.20 m spec
# copied from the placeholder profile. Every plan was refused for being legal.
