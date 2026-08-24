"""L2a/b — the slicing tree, and realising it against an envelope.

A binary `Cut` splits its rectangle so the two sides receive **net** area in
proportion to their demand — net, because that is the only area the programme is
written in and the only one code minima apply to. Splitting net area is what
makes the leaves come out exact: each cut first takes its own wall out of the
run, then divides what is left, so by the time a leaf is reached the arithmetic
has already paid for every wall above it.

A structural cut then snaps to the grid and the two sides absorb the tolerance,
exactly as ARCHITECTURE section 5 requires. A partition cut is free and stays
exact.

A `BandCut` splits its rectangle in three — room, corridor, room — and is the
structural reason the output is a distributed plan rather than a composition
(ARCHITECTURE section 4). The band is given a clear width and its length falls
out of the plan, so its area is never taken from demand. A T-spine is a band cut
nested inside one child of another band cut.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Iterator

from planfgen.brief.plan import Brief
from planfgen.brief.programme import Programme, RoomSpec
from planfgen.brief.regulation import RegulationProfile
from planfgen.fabric.axis import WallKind
from planfgen.partition.grid import StructuralGrid
from planfgen.partition.plan import PartitionPlan, SpaceCell

#: Smallest sliver a cut may leave on either side, in metres.
MIN_SIDE = 1e-6

#: A band is always walled in cloisons — it is circulation, never structure.
BAND_WALL = WallKind.CLOISON


class Direction(Enum):
    """The orientation of the cut line itself.

    `V` is a vertical line, so it splits the rectangle into left and right.
    `H` is a horizontal line, so it splits it into bottom and top. In both
    cases `children[0]` is the low side — left, or bottom.
    """

    H = "h"
    V = "v"


@dataclass(frozen=True)
class Leaf:
    """One room of the programme, not yet placed."""

    nom: str


@dataclass(frozen=True)
class Cut:
    """A split of one rectangle into two, carrying a wall."""

    direction: Direction
    structural: bool
    children: tuple[Node, Node]

    @property
    def wall_kind(self) -> WallKind:
        """A structural cut carries a bearing wall; a free one carries a cloison."""
        return WallKind.PORTEUR if self.structural else WallKind.CLOISON


@dataclass(frozen=True)
class BandCut:
    """A split of one rectangle into three: child, circulation band, child.

    The band is implicit — it has no node of its own, because it is not
    something the programme asked to be sized. It is given a clear width and
    takes whatever length the rectangle happens to have, and the two children
    are proportioned out of what is left.

    `width_source` names the regulation value the clear width comes from, so a
    PMR-width spine costs nothing to express. The field is declared after
    `children` rather than between it and `direction`, because a defaulted
    dataclass field cannot precede one without a default.
    """

    direction: Direction
    children: tuple[Node, Node]
    width_source: str = "corridor"

    def clear_width(self, profile: RegulationProfile) -> float:
        """The width someone actually walks through, in m."""
        if self.width_source == "corridor":
            return profile.corridor_clear
        if self.width_source == "pmr":
            return profile.pmr_circle
        raise ValueError(
            f"unknown width_source {self.width_source!r}; "
            f"expected 'corridor' or 'pmr'"
        )

    def axis_width(self, profile: RegulationProfile) -> float:
        """The band measured on the wall centrelines.

        ARCHITECTURE section 4: `corridor_clear + (t_left + t_right) / 2`, and
        both band walls are cloisons, so this is `clear + cloison_t`.
        """
        return self.clear_width(profile) + profile.thickness_of(BAND_WALL.value)


Node = Leaf | Cut | BandCut


@dataclass(frozen=True)
class SlicingTree:
    """The structure of the plan, independent of any envelope."""

    root: Node

    def leaves(self) -> list[Leaf]:
        """Every leaf, left to right in tree order. Bands are not leaves."""
        out: list[Leaf] = []
        _collect(self.root, out)
        return out

    def bands(self) -> list[BandCut]:
        """Every band, in the order `realise` will name them."""
        out: list[BandCut] = []
        _collect_bands(self.root, out)
        return out

    def demand(self, node: Node, programme: Programme) -> float:
        """Total net area, in m2, the programme asks for below this node.

        A band contributes nothing: its area is an output, so whatever the
        programme happened to declare for the corridor is ignored here by
        design — see ARCHITECTURE section 4.
        """
        if isinstance(node, Leaf):
            return programme.by_nom(node.nom).surface_utile
        return sum(self.demand(child, programme) for child in node.children)

    def realise(
        self,
        rect: tuple[float, float, float, float],
        brief: Brief,
        grid: StructuralGrid,
    ) -> PartitionPlan:
        """Place every leaf inside `rect`, which is (x, y, w, h) on the axes.

        The four outer edges are FACADE; every internal edge takes the kind of
        the cut that made it. Bands are named from the programme's circulation
        rooms, in tree order.
        """
        kinds = dict.fromkeys(("left", "right", "bottom", "top"), WallKind.FACADE)
        cells: list[SpaceCell] = []
        names = iter(brief.programme.circulation_rooms)
        self._place(self.root, rect, kinds, brief, grid, cells, names)
        return PartitionPlan(cells=cells, grid=grid, envelope_rect=rect, brief=brief)

    def _place(self, node, rect, kinds, brief, grid, cells, names) -> None:
        x, y, w, h = rect
        if isinstance(node, Leaf):
            cells.append(SpaceCell(node.nom, x, y, w, h, dict(kinds)))
            return

        profile = brief.profile
        t = {side: profile.thickness_of(kind.value) for side, kind in kinds.items()}
        low, high = node.children
        d_low = self.demand(low, brief.programme)
        d_total = d_low + self.demand(high, brief.programme)
        if d_total <= 0:
            raise ValueError("a cut whose children demand no area cannot be placed")
        share = d_low / d_total

        if isinstance(node, BandCut):
            self._place_band(node, rect, kinds, t, share, brief, grid, cells, names)
            return

        wall = node.wall_kind
        t_cut = profile.thickness_of(wall.value)
        if node.direction is Direction.V:
            free = w - (t["left"] + t["right"]) / 2 - t_cut
            _require(free, w, t_cut, "run")
            offset = free * share + (t["left"] + t_cut) / 2
            offset = self._snapped(node, x, offset, w, grid, "x")
            self._place(low, (x, y, offset, h), {**kinds, "right": wall},
                        brief, grid, cells, names)
            self._place(high, (x + offset, y, w - offset, h), {**kinds, "left": wall},
                        brief, grid, cells, names)
        else:
            free = h - (t["bottom"] + t["top"]) / 2 - t_cut
            _require(free, h, t_cut, "rise")
            offset = free * share + (t["bottom"] + t_cut) / 2
            offset = self._snapped(node, y, offset, h, grid, "y")
            self._place(low, (x, y, w, offset), {**kinds, "top": wall},
                        brief, grid, cells, names)
            self._place(high, (x, y + offset, w, h - offset), {**kinds, "bottom": wall},
                        brief, grid, cells, names)

    def _place_band(
        self, node, rect, kinds, t, share, brief, grid, cells, names
    ) -> None:
        """Room, band, room. The band's width is spent before anything is shared."""
        x, y, w, h = rect
        profile = brief.profile
        t_band = profile.thickness_of(BAND_WALL.value)
        clear = node.clear_width(profile)
        band_axis = node.axis_width(profile)
        low, high = node.children
        nom = _next_band_nom(names)

        if node.direction is Direction.V:
            free = w - (t["left"] + t["right"]) / 2 - 2 * t_band - clear
            _require(free, w, band_axis, "run")
            w_low = free * share + (t["left"] + t_band) / 2
            band_x = x + w_low
            self._place(low, (x, y, w_low, h), {**kinds, "right": BAND_WALL},
                        brief, grid, cells, names)
            cells.append(
                SpaceCell(
                    nom, band_x, y, band_axis, h,
                    {**kinds, "left": BAND_WALL, "right": BAND_WALL},
                    is_band=True,
                )
            )
            start = band_x + band_axis
            self._place(high, (start, y, x + w - start, h),
                        {**kinds, "left": BAND_WALL}, brief, grid, cells, names)
        else:
            free = h - (t["bottom"] + t["top"]) / 2 - 2 * t_band - clear
            _require(free, h, band_axis, "rise")
            h_low = free * share + (t["bottom"] + t_band) / 2
            band_y = y + h_low
            self._place(low, (x, y, w, h_low), {**kinds, "top": BAND_WALL},
                        brief, grid, cells, names)
            cells.append(
                SpaceCell(
                    nom, x, band_y, w, band_axis,
                    {**kinds, "bottom": BAND_WALL, "top": BAND_WALL},
                    is_band=True,
                )
            )
            start = band_y + band_axis
            self._place(high, (x, start, w, y + h - start),
                        {**kinds, "bottom": BAND_WALL}, brief, grid, cells, names)

    @staticmethod
    def _snapped(node, start, offset, extent, grid, axis) -> float:
        """Pull a structural cut onto the grid, unless that would erase a side."""
        if not node.structural:
            return offset
        snapped = grid.snap(start + offset, axis) - start
        if MIN_SIDE < snapped < extent - MIN_SIDE:
            return snapped
        return offset

    @classmethod
    def from_sequence(
        cls, noms: list[str], seed: int, structural: bool = False
    ) -> SlicingTree:
        """A balanced tree over `noms`, with `seed` choosing each cut direction."""
        if not noms:
            raise ValueError("a slicing tree needs at least one room")
        return cls(root=_balanced(list(noms), random.Random(seed), structural))


def _require(free: float, extent: float, consumed: float, run: str) -> None:
    if free <= 0:
        raise ValueError(
            f"a {extent:.3f} m {run} cannot host {consumed:.2f} m of wall "
            f"and two rooms"
        )


def _next_band_nom(names: Iterator[RoomSpec]) -> str:
    """Bands are named from the programme's circulation rooms, in tree order."""
    room = next(names, None)
    if room is None:
        raise ValueError(
            "the tree has more bands than the programme has circulation rooms; "
            "add a COULOIR or ENTREE for each one"
        )
    return room.nom


def _collect(node: Node, out: list[Leaf]) -> None:
    if isinstance(node, Leaf):
        out.append(node)
        return
    for child in node.children:
        _collect(child, out)


def _collect_bands(node: Node, out: list[BandCut]) -> None:
    if isinstance(node, Leaf):
        return
    if isinstance(node, BandCut):
        out.append(node)
    for child in node.children:
        _collect_bands(child, out)


def _balanced(noms: list[str], rng: random.Random, structural: bool) -> Node:
    if len(noms) == 1:
        return Leaf(noms[0])
    half = len(noms) // 2
    return Cut(
        direction=rng.choice(list(Direction)),
        structural=structural,
        children=(
            _balanced(noms[:half], rng, structural),
            _balanced(noms[half:], rng, structural),
        ),
    )
