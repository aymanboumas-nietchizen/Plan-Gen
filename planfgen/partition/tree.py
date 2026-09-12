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
from planfgen.brief.programme import Programme
from planfgen.brief.regulation import RegulationProfile
from planfgen.fabric.axis import WallKind
from planfgen.partition.grid import StructuralGrid
from planfgen.partition.plan import PartitionPlan, SpaceCell

#: Smallest sliver a cut may leave on either side, in metres.
MIN_SIDE = 1e-6

#: A band is always walled in cloisons — it is circulation, never structure.
BAND_WALL = WallKind.CLOISON

#: How many times `realise` may repeat its pass to even out an unbalanced tree.
REFINE_PASSES = 12

#: Relative area error at which refinement stops: exact for this purpose.
REFINE_TOL = 1e-12

#: A working demand is never nudged below this, in m2.
MIN_DEMAND = 1e-6


class UnrealisableTree(ValueError):
    """The tree cannot be realised on **any** envelope.

    A band with no spare circulation room to name it, a room placed twice, a cut
    whose children ask for nothing, a `width_source` that names no regulation
    value: none of these are made better by a larger rectangle. They are
    properties of the tree and the programme alone, and the answer is the same
    at every area.

    A `ValueError` because that is what these have always been raised as, and a
    *subclass* because a caller that answers a realise failure by enlarging the
    footprint — `brief.footprint._bracket` does exactly that — has to be able to
    tell it apart from `EnvelopeTooTight`. Left indistinguishable, the solve
    grows the building until it runs out of patience and then blames the site.
    """


class EnvelopeTooTight(ValueError):
    """This rectangle cannot host this subtree's walls; a larger one may.

    The only realise failure a bigger footprint can fix, and therefore the only
    one the footprint solve is allowed to read as an undershoot.
    """


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
        raise UnrealisableTree(
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

    def band_names(self, programme: Programme) -> list[str]:
        """The circulation rooms available to name this tree's bands, in order.

        A circulation room already standing as a `Leaf` is a room, not a spine,
        and is not in the pool: taking its nom for a band would place the same
        room twice. This is the rule `_pass` names bands by, published so that
        a caller proposing bands — the search's `insert_band` — can count them
        without guessing.
        """
        leaf_noms = {leaf.nom for leaf in self.leaves()}
        return [
            room.nom
            for room in programme.circulation_rooms
            if room.nom not in leaf_noms
        ]

    def check_nameable(self, programme: Programme) -> None:
        """Raise `UnrealisableTree` if there are more bands than names for them.

        Checked before any geometry, because no envelope changes the answer.
        Discovered late — mid-placement, at whatever rectangle happened to be
        tried — this reads like a failure *of that rectangle*, and a caller that
        answers those by enlarging the footprint will enlarge it forever.
        """
        bands, names = len(self.bands()), len(self.band_names(programme))
        if bands > names:
            raise UnrealisableTree(_no_name_for_band(bands, names))

    def demand(self, node: Node, programme: Programme) -> float:
        """Total net area, in m2, the programme asks for below this node.

        A band contributes nothing: its area is an output, so whatever the
        programme happened to declare for the corridor is ignored here by
        design — see ARCHITECTURE section 4.
        """
        return self._demand(node, _targets(self, programme))

    def _demand(self, node: Node, demands: dict[str, float]) -> float:
        """Demand below a node, read from a working dict rather than the brief."""
        if isinstance(node, Leaf):
            return demands[node.nom]
        return sum(self._demand(child, demands) for child in node.children)

    def realise(
        self,
        rect: tuple[float, float, float, float],
        brief: Brief,
        grid: StructuralGrid,
        refine: int = REFINE_PASSES,
    ) -> PartitionPlan:
        """Place every leaf inside `rect`, which is (x, y, w, h) on the axes.

        The four outer edges are FACADE; every internal edge takes the kind of
        the cut that made it. Bands are named from the programme's circulation
        rooms, in tree order.

        A single top-down pass cannot be exact on an unbalanced tree. Each cut
        pays for its own wall and divides what is left, but it cannot know that
        one side will spend more on walls below it than the other, so shallow
        leaves come out over and deep leaves under. There is no closed form to
        reach for: the area a subtree can deliver depends on how it is split,
        and the split depends on the area — so the pass is repeated against a
        working demand that is nudged toward the measured shortfall, and the
        best of the passes is kept. Balanced trees converge on the first pass;
        `refine=0` gives the plain single pass.

        The working demands are renormalised to the programme's total on every
        pass, so refinement only ever *redistributes*. When the envelope cannot
        deliver what was asked, the right answer is the same relative shortfall
        everywhere, and chasing it room by room would only make it uneven.
        """
        self.check_nameable(brief.programme)
        targets = _targets(self, brief.programme)
        working = dict(targets)
        best = current = self._pass(rect, brief, grid, working)
        best_spread = _spread(current, targets, brief.profile)

        for _ in range(refine):
            if best_spread <= REFINE_TOL:
                break
            nudged = _nudge(working, targets, current, brief.profile)
            if nudged is None:
                break
            working = nudged
            try:
                current = self._pass(rect, brief, grid, working)
            except EnvelopeTooTight:
                break
            spread = _spread(current, targets, brief.profile)
            if spread < best_spread:
                best, best_spread = current, spread
        return best

    def _pass(
        self,
        rect: tuple[float, float, float, float],
        brief: Brief,
        grid: StructuralGrid,
        demands: dict[str, float],
    ) -> PartitionPlan:
        """One top-down placement against a given set of demands."""
        kinds = dict.fromkeys(("left", "right", "bottom", "top"), WallKind.FACADE)
        cells: list[SpaceCell] = []
        names = iter(self.band_names(brief.programme))
        self._place(self.root, rect, kinds, brief, grid, cells, names, demands)
        _no_duplicates(cells)
        return PartitionPlan(cells=cells, grid=grid, envelope_rect=rect, brief=brief)

    def _place(self, node, rect, kinds, brief, grid, cells, names, demands) -> None:
        x, y, w, h = rect
        if isinstance(node, Leaf):
            cells.append(SpaceCell(node.nom, x, y, w, h, dict(kinds)))
            return

        profile = brief.profile
        t = {side: profile.thickness_of(kind.value) for side, kind in kinds.items()}
        low, high = node.children
        d_low = self._demand(low, demands)
        d_total = d_low + self._demand(high, demands)
        if d_total <= 0:
            raise UnrealisableTree(
                "a cut whose children demand no area cannot be placed"
            )
        share = d_low / d_total

        if isinstance(node, BandCut):
            self._place_band(node, rect, kinds, t, share, brief, grid, cells,
                             names, demands)
            return

        wall = node.wall_kind
        t_cut = profile.thickness_of(wall.value)
        if node.direction is Direction.V:
            free = w - (t["left"] + t["right"]) / 2 - t_cut
            _require(free, w, t_cut, "run")
            offset = free * share + (t["left"] + t_cut) / 2
            offset = self._snapped(node, x, offset, w, grid, "x")
            self._place(low, (x, y, offset, h), {**kinds, "right": wall},
                        brief, grid, cells, names, demands)
            self._place(high, (x + offset, y, w - offset, h), {**kinds, "left": wall},
                        brief, grid, cells, names, demands)
        else:
            free = h - (t["bottom"] + t["top"]) / 2 - t_cut
            _require(free, h, t_cut, "rise")
            offset = free * share + (t["bottom"] + t_cut) / 2
            offset = self._snapped(node, y, offset, h, grid, "y")
            self._place(low, (x, y, w, offset), {**kinds, "top": wall},
                        brief, grid, cells, names, demands)
            self._place(high, (x, y + offset, w, h - offset), {**kinds, "bottom": wall},
                        brief, grid, cells, names, demands)

    def _place_band(
        self, node, rect, kinds, t, share, brief, grid, cells, names, demands
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
                        brief, grid, cells, names, demands)
            cells.append(
                SpaceCell(
                    nom, band_x, y, band_axis, h,
                    {**kinds, "left": BAND_WALL, "right": BAND_WALL},
                    is_band=True,
                )
            )
            start = band_x + band_axis
            self._place(high, (start, y, x + w - start, h),
                        {**kinds, "left": BAND_WALL}, brief, grid, cells, names, demands)
        else:
            free = h - (t["bottom"] + t["top"]) / 2 - 2 * t_band - clear
            _require(free, h, band_axis, "rise")
            h_low = free * share + (t["bottom"] + t_band) / 2
            band_y = y + h_low
            self._place(low, (x, y, w, h_low), {**kinds, "top": BAND_WALL},
                        brief, grid, cells, names, demands)
            cells.append(
                SpaceCell(
                    nom, x, band_y, w, band_axis,
                    {**kinds, "bottom": BAND_WALL, "top": BAND_WALL},
                    is_band=True,
                )
            )
            start = band_y + band_axis
            self._place(high, (x, start, w, y + h - start),
                        {**kinds, "bottom": BAND_WALL}, brief, grid, cells, names, demands)

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


def _targets(tree: SlicingTree, programme: Programme) -> dict[str, float]:
    """The net area each leaf is asking for. Bands are not leaves, so not here."""
    return {leaf.nom: programme.by_nom(leaf.nom).surface_utile for leaf in tree.leaves()}


def _spread(plan: PartitionPlan, targets: dict[str, float], profile) -> float:
    """The worst relative area error over the rooms that have a target."""
    worst = 0.0
    for cell in plan.cells:
        if cell.is_band:
            continue
        target = targets[cell.nom]
        worst = max(worst, abs(cell.net_area(profile) / target - 1.0))
    return worst


def _nudge(
    working: dict[str, float],
    targets: dict[str, float],
    plan: PartitionPlan,
    profile,
) -> dict[str, float] | None:
    """Ask each room for what it was short, then rescale to the original total.

    Rescaling is the point. If the envelope simply cannot deliver what the
    programme asked for, every room is short by the same fraction and there is
    nothing to fix; without the rescale the demands would inflate every pass and
    the shortfall would look worse each time. With it, only the *distribution*
    moves, which is the part an unbalanced tree actually gets wrong.
    """
    delivered = {c.nom: c.net_area(profile) for c in plan.cells if not c.is_band}
    if any(area <= 0 for area in delivered.values()):
        return None

    nudged = {
        nom: max(MIN_DEMAND, value * targets[nom] / delivered[nom])
        for nom, value in working.items()
    }
    total = sum(nudged.values())
    if total <= 0:
        return None
    scale = sum(targets.values()) / total
    return {nom: value * scale for nom, value in nudged.items()}


def _require(free: float, extent: float, consumed: float, run: str) -> None:
    if free <= 0:
        raise EnvelopeTooTight(
            f"a {extent:.3f} m {run} cannot host {consumed:.2f} m of wall "
            f"and two rooms"
        )


def _no_name_for_band(bands: int | None = None, names: int | None = None) -> str:
    """The one wording for a band nobody can name, counted where it is known."""
    counted = (
        f": {bands} band(s), {names} spare name(s)" if bands is not None else ""
    )
    return (
        f"the tree has more bands than it has spare circulation rooms to name "
        f"them{counted}; add a COULOIR or ENTREE per band, and note that a "
        f"circulation room standing as a Leaf is not available to name one"
    )


def _next_band_nom(names: Iterator[str]) -> str:
    """Bands are named from `band_names`, in tree order.

    The backstop. `realise` calls `check_nameable` before any geometry, so this
    is only reached by a caller that placed without going through `realise`.
    """
    nom = next(names, None)
    if nom is None:
        raise UnrealisableTree(_no_name_for_band())
    return nom


def _no_duplicates(cells: list[SpaceCell]) -> None:
    """No room may be placed twice. Caught here, not three layers downstream."""
    seen: set[str] = set()
    twice: set[str] = set()
    for placed in cells:
        if placed.nom in seen:
            twice.add(placed.nom)
        seen.add(placed.nom)
    if twice:
        raise UnrealisableTree(
            f"placed more than once: {', '.join(sorted(twice))}; a room is either a "
            f"leaf or a band, never both"
        )


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
