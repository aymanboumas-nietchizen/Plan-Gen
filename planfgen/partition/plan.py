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
    #: True if this cell is a circulation band. Its area is an output of the
    #: partition, not something the programme asked for, so the area gates
    #: skip it — see ARCHITECTURE section 4.
    is_band: bool = False

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
        """True if no room is too elongated to furnish, measured on net dims.

        Bands are exempt. A corridor is supposed to be long and thin, and it is
        never furnished, so judging it by a room's aspect ratio would fail every
        plan that has one. What governs a band is its clear width.
        """
        profile = self.brief.profile
        return all(
            aspect_ok(*cell.net_dims(profile), max_ratio)
            for cell in self.cells
            if not cell.is_band
        )

    def area_error(self, profile: RegulationProfile) -> dict[str, float]:
        """Signed relative error per room: positive means the cell is too big.

        Bands are left out. A corridor gets a width, never an area, so there is
        no target to be in error against — measure it with
        `circulation_coefficient` instead.
        """
        programme = self.brief.programme
        return {
            cell.nom: cell.net_area(profile) / programme.by_nom(cell.nom).surface_utile
            - 1.0
            for cell in self.cells
            if not cell.is_band
        }

    @property
    def circulation_cells(self) -> list[SpaceCell]:
        """The cells the programme types as circulation."""
        programme = self.brief.programme
        return [
            cell
            for cell in self.cells
            if programme.by_nom(cell.nom).kind.is_circulation
        ]

    def circulation_coefficient(self, profile: RegulationProfile) -> float:
        """Circulation net area over total net area.

        This is the number `"Couloir": {"surface": 7}` was trying and failing to
        control. It is a result, read off the finished tiling.
        """
        total = self.total_net(profile)
        if total <= 0:
            return 0.0
        return sum(c.net_area(profile) for c in self.circulation_cells) / total

    def band_clear_width(self, cell: SpaceCell, profile: RegulationProfile) -> float:
        """The narrow net dimension of a band — what someone walks through."""
        return min(cell.net_dims(profile))

    def max_area_error(self, profile: RegulationProfile) -> float:
        """The worst absolute relative error over all rooms."""
        errors = self.area_error(profile)
        return max((abs(e) for e in errors.values()), default=0.0)

    def total_net(self, profile: RegulationProfile) -> float:
        """Sum of the net areas the tiling actually delivers, in m²."""
        return sum(cell.net_area(profile) for cell in self.cells)

    def to_wall_graph(self, profile: RegulationProfile):
        """Author this tiling's cut lines as a `WallGraph`.

        An edge shared by two cells becomes one axis, and where the two cells
        disagree about its kind the thicker wall wins.
        """
        from planfgen.partition.bridge import to_wall_graph

        return to_wall_graph(self, profile)

    def to_fabric(self, profile: RegulationProfile):
        """Cross into L3: node the graph and read the spaces back out as faces.

        This is where the rooms stop being authored. What comes back is derived
        from the walls, and its net areas are measured, not promised.
        """
        from planfgen.partition.bridge import to_fabric

        return to_fabric(self, profile)
