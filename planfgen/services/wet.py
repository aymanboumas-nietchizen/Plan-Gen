"""L4 — wet walls: the ones that have to be thick enough to hide a pipe.

Retyping a wall to `WET` is not a label. `WET` is 0.20 m against a cloison's
0.10, so every room on a retyped wall loses 0.05 m of net width, and a room that
was exactly on its target is not any more. `assign_wet_walls` therefore
re-solidifies the spaces it touched: leaving them stale would break L3's own
guarantee that its net areas are real, and would do it silently.
"""

from __future__ import annotations

from planfgen.fabric.axis import WallAxis, WallKind
from planfgen.fabric.plan import FabricPlan, Space
from planfgen.fabric.solidify import net_polygon
from planfgen.services.shaft import Shaft


def _wet_walls(fabric: FabricPlan, shafts: list[Shaft]) -> list[WallAxis]:
    """Walls between two wet rooms, or carrying a shaft.

    Facades are left alone. A wall between a bathroom and the street is not a
    wet wall; it is the outside, and thickening it would take area off the room
    for nothing.
    """
    wet_noms = [nom for nom, space in fabric.spaces.items() if space.kind.is_wet]
    found: list[WallAxis] = []

    def keep(wall: WallAxis | None) -> None:
        if wall is None or wall.kind is WallKind.FACADE:
            return
        if not any(wall is seen for seen in found):
            found.append(wall)

    for i, a in enumerate(wet_noms):
        for b in wet_noms[i + 1 :]:
            keep(
                fabric.graph.wall_between(
                    fabric.spaces[a].axis_polygon, fabric.spaces[b].axis_polygon
                )
            )

    for nom in wet_noms:
        for wall in fabric.spaces[nom].bounding:
            if any(shaft.on_wall(wall) for shaft in shafts):
                keep(wall)
    return found


def assign_wet_walls(fabric: FabricPlan, shafts: list[Shaft]) -> None:
    """Retype the walls that carry plumbing, and re-measure what that costs."""
    retyped = _wet_walls(fabric, shafts)
    if not retyped:
        return
    for wall in retyped:
        wall.kind = WallKind.WET

    touched = {id(wall) for wall in retyped}
    for nom, space in fabric.spaces.items():
        if not any(id(wall) in touched for wall in space.bounding):
            continue
        fabric.spaces[nom] = Space(
            nom=space.nom,
            kind=space.kind,
            axis_polygon=space.axis_polygon,
            net_polygon=net_polygon(space.axis_polygon, space.bounding, fabric.profile),
            bounding=space.bounding,
        )


def wet_report(fabric: FabricPlan, shafts: list[Shaft]) -> dict[str, bool]:
    """Per wet room, whether one of its own walls carries a shaft.

    Only wet rooms appear. A chambre has no opinion about plumbing, and padding
    the report with rooms that always pass would hide the ones that do not.
    """
    return {
        nom: any(
            shaft.on_wall(wall) for wall in space.bounding for shaft in shafts
        )
        for nom, space in fabric.spaces.items()
        if space.kind.is_wet
    }
