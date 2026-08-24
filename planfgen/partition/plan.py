"""L2a — `SpaceCell` and `PartitionPlan`: the tiling, before it becomes walls.

A cell is still only a rectangle on the axes; L3 turns the cut lines into a wall
graph and reads the spaces back out. What this layer guarantees is that the
tiling is exact — every cell positive, no gap, no overlap — and that the net
areas it reports are the ones the closed form of ARCHITECTURE section 2 gives.
"""

from __future__ import annotations

from dataclasses import dataclass

from planfgen.brief.plan import Brief
from planfgen.brief.regulation import RegulationProfile
from planfgen.fabric.axis import WallKind
from planfgen.partition.grid import StructuralGrid
from planfgen.partition.sizing import aspect_ok

#: The four sides of a cell, in the order the wall_kinds dict is keyed.
SIDES = ("left", "right", "bottom", "top")


@dataclass
class SpaceCell:
    """One leaf of the slicing tree, placed. `x, y` is the lower-left corner."""

    nom: str
    x: float
    y: float
    w: float
    h: float
    wall_kinds: dict[str, WallKind]

    @property
    def axis_area(self) -> float:
        """Area measured on the wall centrelines, in m²."""
        return self.w * self.h

    def net_dims(self, profile: RegulationProfile) -> tuple[float, float]:
        """(net_w, net_h) — half of each bounding wall removed."""
        t = {side: profile.thickness_of(self.wall_kinds[side].value) for side in SIDES}
        return (
            self.w - (t["left"] + t["right"]) / 2,
            self.h - (t["bottom"] + t["top"]) / 2,
        )

    def net_area(self, profile: RegulationProfile) -> float:
        """Habitable area in m². This is what code minima apply to."""
        net_w, net_h = self.net_dims(profile)
        return net_w * net_h


@dataclass
class PartitionPlan:
    """A complete tiling of the envelope, one cell per room."""

    cells: list[SpaceCell]
    grid: StructuralGrid
    envelope_rect: tuple[float, float, float, float]
    brief: Brief

    def aspects_ok(self, max_ratio: float = 2.5) -> bool:
        """True if no room is too elongated to furnish, measured on net dims."""
        profile = self.brief.profile
        return all(aspect_ok(*cell.net_dims(profile), max_ratio) for cell in self.cells)

    def area_error(self, profile: RegulationProfile) -> dict[str, float]:
        """Signed relative error per room: positive means the cell is too big."""
        programme = self.brief.programme
        return {
            cell.nom: cell.net_area(profile) / programme.by_nom(cell.nom).surface_utile
            - 1.0
            for cell in self.cells
        }

    def max_area_error(self, profile: RegulationProfile) -> float:
        """The worst absolute relative error over all rooms."""
        errors = self.area_error(profile)
        return max((abs(e) for e in errors.values()), default=0.0)

    def total_net(self, profile: RegulationProfile) -> float:
        """Sum of the net areas the tiling actually delivers, in m²."""
        return sum(cell.net_area(profile) for cell in self.cells)
