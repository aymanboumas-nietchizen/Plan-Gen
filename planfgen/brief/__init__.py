"""L0 — `brief/`: the programme, the parcel, the regulation and the gate.

Produces a `Brief`, guaranteeing that the programme fits the parcel, that every
outline edge is typed, and that north is known.
"""

from planfgen.brief.feasibility import (
    AreaBudget,
    check_feasibility,
    estimate_partition_length,
)
from planfgen.brief.parcel import EdgeSpec, EdgeType, Parcel
from planfgen.brief.plan import Brief, InfeasibleBrief
from planfgen.brief.programme import Orientation, Programme, RoomSpec, RoomType
from planfgen.brief.regulation import MA_PROFILE, RegulationProfile

__all__ = [
    "AreaBudget",
    "Brief",
    "EdgeSpec",
    "EdgeType",
    "InfeasibleBrief",
    "MA_PROFILE",
    "Orientation",
    "Parcel",
    "Programme",
    "RegulationProfile",
    "RoomSpec",
    "RoomType",
    "check_feasibility",
    "estimate_partition_length",
]
