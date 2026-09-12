"""L0 — `brief/`: the programme, the parcel, the regulation and the gate.

Produces a `Brief`, guaranteeing that the programme fits the parcel, that every
outline edge is typed, and that north is known.
"""

from planfgen.brief.feasibility import (
    AreaBudget,
    check_feasibility,
    estimate_partition_length,
)
from planfgen.brief.footprint import (
    Footprint,
    delivered,
    fit_brief,
    fit_footprint,
    fit_programme,
    place_footprint,
    scale_for,
    sized_demand,
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
    "Footprint",
    "InfeasibleBrief",
    "MA_PROFILE",
    "Orientation",
    "Parcel",
    "Programme",
    "RegulationProfile",
    "RoomSpec",
    "RoomType",
    "check_feasibility",
    "delivered",
    "estimate_partition_length",
    "fit_brief",
    "fit_footprint",
    "fit_programme",
    "place_footprint",
    "scale_for",
    "sized_demand",
]
