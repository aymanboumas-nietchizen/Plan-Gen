"""L7 — `habitability/`: whether a room can actually be used.

Area says nothing about shape. ARCHITECTURE section 1 measured a v1 chambre of
11.25 m2 whose largest inscribed rectangle was 1.30 x 1.75 m — no bed fits.
"""

from planfgen.habitability.check import (
    TableConflict,
    fit_report,
    fits,
    table_conflicts,
)
from planfgen.habitability.furniture import FURNITURE, FurnitureSpec

__all__ = [
    "FURNITURE",
    "FurnitureSpec",
    "TableConflict",
    "fit_report",
    "fits",
    "table_conflicts",
]
