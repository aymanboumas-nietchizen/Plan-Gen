"""L7 — does the furniture fit? Two float comparisons, and nothing else.

This runs inside the search loop, so it touches no polygon and allocates almost
nothing. A `Space` knows its own net dimensions; a `SpaceCell` needs the profile
to work them out, which is the only reason `fits` takes one.
"""

from __future__ import annotations

from planfgen.brief.regulation import RegulationProfile
from planfgen.habitability.furniture import FURNITURE, FurnitureSpec


def fits(space_or_cell, spec: FurnitureSpec, profile: RegulationProfile | None = None) -> bool:
    """True if `spec`'s rectangle fits inside the room's net rectangle.

    Pass `profile` for a `SpaceCell`, which cannot work out its own net
    dimensions; a `Space` already carries its net polygon and needs none.
    """
    width, height = (
        space_or_cell.net_dims() if profile is None else space_or_cell.net_dims(profile)
    )
    short, long = (width, height) if width <= height else (height, width)
    return short >= spec.min_side and long >= spec.min_long


def fit_report(plan, profile: RegulationProfile) -> dict[str, bool]:
    """Per room, whether its furniture fits. Rooms with no spec always pass.

    Accepts either a `FabricPlan`, whose spaces know their own kind, or a
    `PartitionPlan`, whose cells do not and are looked up in the programme.
    """
    if hasattr(plan, "spaces"):
        rooms = [(s.nom, s.kind, s, None) for s in plan.spaces.values()]
    else:
        programme = plan.brief.programme
        rooms = [
            (c.nom, programme.by_nom(c.nom).kind, c, profile) for c in plan.cells
        ]

    report: dict[str, bool] = {}
    for nom, kind, room, arg in rooms:
        spec = FURNITURE.get(kind)
        report[nom] = True if spec is None else fits(room, spec, arg)
    return report
