"""L7 — does the furniture fit? Two float comparisons, and nothing else.

This runs inside the search loop, so it touches no polygon and allocates almost
nothing. A `Space` knows its own net dimensions; a `SpaceCell` needs the profile
to work them out, which is the only reason `fits` takes one.
"""

from __future__ import annotations

from dataclasses import dataclass

from planfgen.brief.programme import RoomType
from planfgen.brief.regulation import RegulationProfile
from planfgen.habitability.furniture import FURNITURE, FurnitureSpec


def fits(space_or_cell, spec: FurnitureSpec, profile: RegulationProfile | None = None) -> bool:
    """True if the room can hold `spec`'s rectangle AND be arranged around it.

    Pass `profile` for a `SpaceCell`, which cannot work out its own net
    dimensions; a `Space` already carries its net polygon and needs none.
    """
    width, height = (
        space_or_cell.net_dims() if profile is None else space_or_cell.net_dims(profile)
    )
    short, long = (width, height) if width <= height else (height, width)
    if short <= 0:
        return False
    if short < spec.min_side or long < spec.min_long:
        return False
    # A minimum footprint has a floor but no ceiling: 0.92 x 5.17 clears a
    # 0.90 x 1.40 WC twice over and is a corridor with a pan at one end.
    return spec.max_ratio is None or long / short <= spec.max_ratio


def fit_report(plan, profile: RegulationProfile) -> dict[str, bool]:
    """Per room, whether its furniture fits. Rooms with no spec always pass.

    Accepts either a `FabricPlan`, whose spaces know their own kind, or a
    `PartitionPlan`, whose cells do not and are looked up in the programme.
    Bands are not reported: a corridor is not furnished.
    """
    if hasattr(plan, "spaces"):
        rooms = [(s.nom, s.kind, s, None) for s in plan.spaces.values()]
    else:
        programme = plan.brief.programme
        # Bands are skipped: a corridor is not furnished, and its clear width is
        # already exactly `profile.corridor_clear` by construction.
        rooms = [
            (c.nom, programme.by_nom(c.nom).kind, c, profile)
            for c in plan.cells
            if not c.is_band
        ]

    report: dict[str, bool] = {}
    for nom, kind, room, arg in rooms:
        spec = FURNITURE.get(kind)
        report[nom] = True if spec is None else fits(room, spec, arg)
    return report


@dataclass(frozen=True)
class TableConflict:
    """A place where the regulation table and the furniture table disagree."""

    kind: RoomType
    issue: str
    regulation: float
    furniture: float
    detail: str


def table_conflicts(profile: RegulationProfile) -> list[TableConflict]:
    """Where `regulation.py` and `furniture.py` contradict each other.

    Both files carry placeholder numbers, and they were written from different
    sources, so they can disagree without anything failing — a room can be legal
    on area and still have nowhere to put the fixture, or be required to be
    wider than the furniture it stands for.

    This does not decide who is right. It says where somebody has to.
    """
    found: list[TableConflict] = []
    for kind, spec in sorted(FURNITURE.items(), key=lambda kv: kv[0].name):
        footprint = spec.min_side * spec.min_long
        minimum = profile.min_area.get(kind)
        if minimum is not None and footprint > minimum + 1e-9:
            found.append(
                TableConflict(
                    kind,
                    "area",
                    minimum,
                    footprint,
                    f"{kind.name} may legally be {minimum:.2f} m2, but its furniture "
                    f"needs {footprint:.2f} m2 — a room built to the minimum cannot "
                    f"hold what the furniture table says goes in it",
                )
            )
        width = profile.min_width.get(kind)
        if width is not None and width > spec.min_side + 1e-9:
            found.append(
                TableConflict(
                    kind,
                    "width",
                    width,
                    spec.min_side,
                    f"{kind.name} must be {width:.2f} m wide but its furniture only "
                    f"needs {spec.min_side:.2f} m — the width rule is stricter than "
                    f"the thing it stands for",
                )
            )
    return found
