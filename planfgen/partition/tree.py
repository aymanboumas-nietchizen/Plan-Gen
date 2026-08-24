"""L2a — the slicing tree, and realising it against an envelope.

Binary cuts only; the band cut is L2b. A cut splits its rectangle so the two
sides receive **net** area in proportion to their demand — net, because that is
the only area the programme is written in and the only one code minima apply
to. Splitting net area is what makes the leaves come out exact: each cut first
takes its own wall out of the run, then divides what is left, so by the time a
leaf is reached the arithmetic has already paid for every wall above it.

A structural cut then snaps to the grid and the two sides absorb the tolerance,
exactly as ARCHITECTURE section 5 requires. A partition cut is free and stays
exact.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

from planfgen.brief.plan import Brief
from planfgen.brief.programme import Programme
from planfgen.fabric.axis import WallKind
from planfgen.partition.grid import StructuralGrid
from planfgen.partition.plan import PartitionPlan, SpaceCell

#: Smallest sliver a cut may leave on either side, in metres.
MIN_SIDE = 1e-6


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


Node = Leaf | Cut


@dataclass(frozen=True)
class SlicingTree:
    """The structure of the plan, independent of any envelope."""

    root: Node

    def leaves(self) -> list[Leaf]:
        """Every leaf, left to right in tree order."""
        out: list[Leaf] = []
        _collect(self.root, out)
        return out

    def demand(self, node: Node, programme: Programme) -> float:
        """Total net area, in m², the programme asks for below this node."""
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
        the cut that made it.
        """
        kinds = dict.fromkeys(("left", "right", "bottom", "top"), WallKind.FACADE)
        cells: list[SpaceCell] = []
        self._place(self.root, rect, kinds, brief, grid, cells)
        return PartitionPlan(
            cells=cells, grid=grid, envelope_rect=rect, brief=brief
        )

    def _place(self, node, rect, kinds, brief, grid, cells) -> None:
        x, y, w, h = rect
        if isinstance(node, Leaf):
            cells.append(SpaceCell(node.nom, x, y, w, h, dict(kinds)))
            return

        profile = brief.profile
        t = {side: profile.thickness_of(kind.value) for side, kind in kinds.items()}
        wall = node.wall_kind
        t_cut = profile.thickness_of(wall.value)

        low, high = node.children
        d_low = self.demand(low, brief.programme)
        d_total = d_low + self.demand(high, brief.programme)
        if d_total <= 0:
            raise ValueError("a cut whose children demand no area cannot be placed")
        share = d_low / d_total

        if node.direction is Direction.V:
            free = w - (t["left"] + t["right"]) / 2 - t_cut
            if free <= 0:
                raise ValueError(
                    f"a {w:.3f} m run cannot host a {t_cut:.2f} m wall and two rooms"
                )
            offset = free * share + (t["left"] + t_cut) / 2
            offset = self._snapped(node, x, offset, w, grid, "x")
            self._place(low, (x, y, offset, h), {**kinds, "right": wall},
                        brief, grid, cells)
            self._place(high, (x + offset, y, w - offset, h), {**kinds, "left": wall},
                        brief, grid, cells)
        else:
            free = h - (t["bottom"] + t["top"]) / 2 - t_cut
            if free <= 0:
                raise ValueError(
                    f"a {h:.3f} m run cannot host a {t_cut:.2f} m wall and two rooms"
                )
            offset = free * share + (t["bottom"] + t_cut) / 2
            offset = self._snapped(node, y, offset, h, grid, "y")
            self._place(low, (x, y, w, offset), {**kinds, "top": wall},
                        brief, grid, cells)
            self._place(high, (x, y + offset, w, h - offset), {**kinds, "bottom": wall},
                        brief, grid, cells)

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


def _collect(node: Node, out: list[Leaf]) -> None:
    if isinstance(node, Leaf):
        out.append(node)
        return
    for child in node.children:
        _collect(child, out)


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
