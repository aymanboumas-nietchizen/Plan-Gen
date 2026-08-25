"""L0 — the footprint: how much of the parcel is actually built on.

Until this module existed the answer was *all of it*. `envelope_of` returned the
parcel's bounding box, so the building was the site, and three separate things
followed from that one assumption:

- a programme had to be rescaled by hand until it matched the parcel, because a
  larger parcel simply made every room larger;
- coverage could not be gated, though CLAUDE.md names it among the gates, since
  it was trivially 100% by construction;
- a non-rectangular parcel was unusable, because the bounding box of an L
  includes the notch.

A footprint is *chosen*, and choosing it is what reconciles a programme with a
site. Two directions, both cheap:

**Solve the footprint** (`fit_footprint`) — the rooms get exactly the area the
programme asked for and the building takes only as much of the parcel as it
needs. This is the architecturally right answer: a 65 m2 programme on a 160 m2
parcel is a 65 m2 apartment, not one with doubled bedrooms.

**Scale the programme** (`fit_programme`) — the fallback for a parcel too small
to hold the brief. Every room is cut by the same factor and the caller is told
what the factor was.

Both are closed forms rather than searches, and for one reason: the net area a
tree delivers depends on the footprint and the tree alone, never on the targets.
`SlicingTree.realise` renormalises its working demands on every refinement pass,
so the targets govern only the *distribution*. Measured on the 7-room fixture
across parcels from 0.95x to 2.5x the programme, the spread between the
best-served and worst-served room is 0.0000% every time. That makes the area
error a single scalar: one multiply fixes it, and solving the other direction is
a secant on one unknown that lands in four steps.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from shapely.geometry import Polygon

from planfgen.brief.feasibility import check_feasibility, estimate_partition_length
from planfgen.brief.parcel import EdgeType, Parcel
from planfgen.brief.plan import Brief, InfeasibleBrief
from planfgen.brief.programme import Programme
from planfgen.brief.regulation import RegulationProfile

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from planfgen.partition.tree import SlicingTree

#: How close the solved footprint must come to the demanded area, in m².
FIT_TOL = 1e-9

#: Secant steps allowed before the solve is called a failure. Four is what the
#: measurement takes; twelve is room for a badly conditioned tree.
FIT_STEPS = 12

#: Where the bracket starts, as multiples of the demanded net area. A footprint
#: is always larger than the area it delivers — it pays for its own walls.
BRACKET_LOW = 1.05
BRACKET_HIGH = 1.45

#: How far the bracket may be grown looking for a footprint that overshoots.
BRACKET_GROW = 1.3
BRACKET_TRIES = 40

#: Containment slack, in m.
WITHIN_TOL = 1e-9


@dataclass(frozen=True)
class Footprint:
    """The rectangle built on, measured on the *outside* of the façade.

    This is the extent a plan de masse would show, which is also the extent
    coverage is judged on. `envelope_rect` converts it to the axis rectangle a
    slicing tree is realised against, by taking off half the façade — the same
    inset `envelope_of` has always applied to the parcel bounds.
    """

    x: float
    y: float
    w: float
    h: float

    def __post_init__(self) -> None:
        if self.w <= 0 or self.h <= 0:
            raise ValueError(
                f"a footprint must have positive extent, got {self.w} x {self.h}"
            )

    @property
    def area(self) -> float:
        """Gross built area in m², façade included."""
        return self.w * self.h

    @property
    def aspect(self) -> float:
        """Width over height."""
        return self.w / self.h

    def envelope_rect(
        self, profile: RegulationProfile
    ) -> tuple[float, float, float, float]:
        """The axis rect a tree is realised on: the footprint less half the façade.

        That inset is what puts the façade *solids* inside the built extent and
        what makes L2's net areas reconcile with L0's feasibility interior.
        """
        inset = profile.facade_t / 2
        return (self.x + inset, self.y + inset, self.w - 2 * inset, self.h - 2 * inset)

    def polygon(self) -> Polygon:
        """The footprint as a Shapely box."""
        return Polygon(
            [
                (self.x, self.y),
                (self.x + self.w, self.y),
                (self.x + self.w, self.y + self.h),
                (self.x, self.y + self.h),
            ]
        )

    def coverage(self, parcel: Parcel) -> float:
        """Built area over parcel area — the CES, emprise au sol.

        Measured against the parcel *polygon*, not its bounding box, so a
        footprint that spills into the notch of an L reports more than 1.
        """
        return self.area / parcel.outline.area

    def within(self, parcel: Parcel, tol: float = WITHIN_TOL) -> bool:
        """True if the whole footprint lies inside the parcel."""
        return parcel.outline.buffer(tol).contains(self.polygon())

    @classmethod
    def from_envelope(
        cls, rect: tuple[float, float, float, float], profile: RegulationProfile
    ) -> Footprint:
        """The footprint around an axis rect — the inverse of `envelope_rect`."""
        x, y, w, h = rect
        inset = profile.facade_t / 2
        return cls(x - inset, y - inset, w + 2 * inset, h + 2 * inset)

    @classmethod
    def of_parcel(cls, parcel: Parcel) -> Footprint:
        """The parcel's bounding box — what the engine assumed before S14."""
        minx, miny, maxx, maxy = parcel.outline.bounds
        return cls(minx, miny, maxx - minx, maxy - miny)

    def against(self, parcel: Parcel, edge: int) -> Footprint:
        """The same footprint, pushed flush against one edge of the parcel.

        Kept because it says one thing plainly, and S14 needed exactly that. The
        rule a brief is actually placed by is `place_footprint`, which honours
        party walls and setbacks as well as the entry.
        """
        lox, loy, hix, hiy = parcel.buildable_bounds()
        side = parcel.side_of(edge)
        if side == "left":
            return replace(self, x=lox)
        if side == "right":
            return replace(self, x=hix - self.w)
        if side == "bottom":
            return replace(self, y=loy)
        return replace(self, y=hiy - self.h)

    def buildable(self, parcel: Parcel, tol: float = WITHIN_TOL) -> bool:
        """True if the footprint is inside the parcel *and* clear of its
        setbacks. `within` is the weaker test and asks only about the boundary.
        """
        if not self.within(parcel, tol):
            return False
        lox, loy, hix, hiy = parcel.buildable_bounds()
        return (
            self.x >= lox - tol
            and self.y >= loy - tol
            and self.x + self.w <= hix + tol
            and self.y + self.h <= hiy + tol
        )

    @classmethod
    def centred(cls, area: float, aspect: float, parcel: Parcel) -> Footprint:
        """A footprint of this gross area and proportion, centred in the parcel.

        Centred in what may be built on, which is the parcel less its
        setbacks — but centring is only where the solve leaves it.
        `place_footprint` decides where a building actually stands.
        """
        if area <= 0 or aspect <= 0:
            raise ValueError(f"area and aspect must be positive, got {area}, {aspect}")
        h = (area / aspect) ** 0.5
        w = area / h
        lox, loy, hix, hiy = parcel.buildable_bounds()
        return cls(
            x=lox + ((hix - lox) - w) / 2,
            y=loy + ((hiy - loy) - h) / 2,
            w=w,
            h=h,
        )


def sized_demand(programme: Programme, tree: SlicingTree) -> float:
    """Net area in m² the tree's **leaves** ask for.

    Not `programme.total_utile`, and the difference matters. A circulation room
    that names a band is not a leaf: a band is given a clear width and takes
    whatever length the plan hands it, so its declared area is never demanded of
    anything. `total_utile` sums it anyway, which is one of the two reasons
    `check_feasibility` is conservative — it charges the parcel for area the
    partition will never be asked to deliver. This is the figure L2 actually has
    to hit, so this is the figure a footprint is solved against.
    """
    return sum(programme.by_nom(leaf.nom).surface_utile for leaf in tree.leaves())


def delivered(
    footprint: Footprint,
    programme: Programme,
    parcel: Parcel,
    profile: RegulationProfile,
    tree: SlicingTree,
) -> float:
    """Net area in m² the tree hands its leaves on this footprint.

    Bands are excluded for the same reason they are excluded from
    `sized_demand`: a corridor's area is an output.
    """
    brief = _brief(programme, parcel, profile, footprint)
    plan = tree.realise(footprint.envelope_rect(profile), brief, _grid(footprint))
    return sum(cell.net_area(profile) for cell in plan.cells if not cell.is_band)


def fit_footprint(
    programme: Programme,
    parcel: Parcel,
    profile: RegulationProfile,
    tree: SlicingTree,
    aspect: float | None = None,
    tol: float = FIT_TOL,
    max_steps: int = FIT_STEPS,
) -> Footprint:
    """The footprint whose leaves deliver `sized_demand` exactly.

    One unknown — the gross built area — and `delivered` is monotone in it, so a
    secant clamped inside a bracket converges in four steps from `BRACKET_LOW`
    to `BRACKET_HIGH`. `aspect` defaults to the parcel's own proportion.

    Two ways this fails, and they are not the same failure. If the parcel
    cannot deliver the area at all, that is `InfeasibleBrief` and it carries the
    budget that proves it. If the area is there but the *shape* asked for will
    not fit — a square building on a long thin site — that is a `ValueError`
    pointing at the parcel's own proportion, which is containable whenever the
    area is: a footprint sharing the parcel's aspect and holding less than its
    area is smaller than it in both directions. Collapsing the two failures
    would report a site as too small when it is merely the wrong shape for the
    instruction it was given.

    There is a most-elongated footprint the parcel could hold, and this does not
    compute it. It would be a second solve — a more elongated building spends
    more on façade, so the area it needs moves with the aspect — and the shape
    of a building is S15's subject, not this one's.
    """
    demand = sized_demand(programme, tree)
    if demand <= 0:
        raise ValueError("a tree whose leaves demand no area has no footprint")
    if aspect is None:
        minx, miny, maxx, maxy = parcel.outline.bounds
        aspect = (maxx - minx) / (maxy - miny)

    def shortfall(area: float) -> float:
        """Signed: negative means the footprint is too small."""
        return delivered(Footprint.centred(area, aspect, parcel), programme,
                         parcel, profile, tree) - demand

    lo, hi, f_hi = _bracket(shortfall, demand)

    # Secant, clamped into the bracket so a bad step degrades to bisection.
    a, f_a = hi, f_hi
    b = lo + (hi - lo) / 2
    for _ in range(max_steps):
        f_b = shortfall(b)
        if abs(f_b) <= tol:
            break
        if f_b < 0:
            lo = b
        else:
            hi, f_hi = b, f_b
        if abs(f_b - f_a) > 0:
            step = b - f_b * (b - a) / (f_b - f_a)
        else:
            step = (lo + hi) / 2
        a, f_a = b, f_b
        b = step if lo < step < hi else (lo + hi) / 2
    else:
        raise ValueError(
            f"the footprint solve did not converge in {max_steps} steps; "
            f"last residual {shortfall(b):.3e} m2 against a demand of {demand:.2f} m2"
        )

    solved = Footprint.centred(b, aspect, parcel)
    if not solved.buildable(parcel):
        budget = _budget_for(programme, parcel, profile, tree, demand)
        if not budget.ok:
            raise InfeasibleBrief(budget)
        minx, miny, maxx, maxy = parcel.outline.bounds
        own = (maxx - minx) / (maxy - miny)
        raise ValueError(
            f"a {solved.w:.2f} x {solved.h:.2f} m footprint does not fit a "
            f"{maxx - minx:.2f} x {maxy - miny:.2f} m parcel: the area is there "
            f"({-budget.deficit:.2f} m2 of slack) but the aspect {aspect:.2f} is "
            f"not. Omit `aspect` to take the parcel's own {own:.2f}, which always "
            f"fits when the area does"
        )
    return solved


def scale_for(
    programme: Programme,
    footprint: Footprint,
    parcel: Parcel,
    profile: RegulationProfile,
    tree: SlicingTree,
) -> float:
    """What every leaf's target must be multiplied by to match this footprint.

    Below 1 means the footprint cannot deliver the brief and the rooms will come
    out smaller than asked; above 1 means it delivers more.
    """
    return delivered(footprint, programme, parcel, profile, tree) / sized_demand(
        programme, tree
    )


def fit_programme(
    programme: Programme,
    footprint: Footprint,
    parcel: Parcel,
    profile: RegulationProfile,
    tree: SlicingTree,
) -> Programme:
    """The programme rescaled to what this footprint actually delivers.

    One realise and one multiply, because the shortfall is uniform. Circulation
    rooms that name a band keep their declared area untouched — nothing reads
    it, and changing it would suggest otherwise.

    Note that this can produce rooms below their code minimum. It does not
    check: `MIN_AREA_GATE` is the thing that refuses those, and it is a gate
    rather than a step here so that the caller sees *which* room lost its
    legality rather than a single opaque failure.
    """
    scale = scale_for(programme, footprint, parcel, profile, tree)
    placed = {leaf.nom for leaf in tree.leaves()}
    return Programme(
        rooms=[
            replace(room, surface_utile=room.surface_utile * scale)
            if room.nom in placed
            else room
            for room in programme.rooms
        ]
    )


def place_footprint(footprint: Footprint, parcel: Parcel) -> Footprint:
    """Where a building of this size stands on this parcel.

    Three rules, in order, applied independently to each axis:

    1. **Flush to a party wall.** A MITOYEN edge is a boundary built *up to* —
       that is what makes it a party wall — so a setback there is a mistake and
       the building takes the boundary.
    2. **Flush to the entry.** Failing a party wall, address the street: the
       shorter the walk from the boundary to the front door, the better, and a
       building that touches its entry edge cannot fail to have frontage.
    3. **Centred.** With neither, sit in the middle of what is left.

    Setbacks are honoured throughout — "flush" means flush to the buildable
    limit, not to the boundary, and the two differ by whatever the edge asks
    for. A MITOYEN edge that also carries a setback is contradictory; the
    setback wins, because it is the one a building can be refused for.

    This is a rule, not a search. `slide_footprint` is what lets the annealer
    disagree with it.
    """
    lox, loy, hix, hiy = parcel.buildable_bounds()
    sides = parcel.sides()
    entry = parcel.side_of(parcel.entry_edge)

    def place(low: float, high: float, extent: float, near: str, far: str) -> float:
        if _is(sides, near, EdgeType.MITOYEN):
            return low
        if _is(sides, far, EdgeType.MITOYEN):
            return high - extent
        if entry == near:
            return low
        if entry == far:
            return high - extent
        return low + ((high - low) - extent) / 2

    return replace(
        footprint,
        x=place(lox, hix, footprint.w, "left", "right"),
        y=place(loy, hiy, footprint.h, "bottom", "top"),
    )


def _is(sides: dict, side: str, kind: EdgeType) -> bool:
    spec = sides.get(side)
    return spec is not None and spec.kind is kind


def fit_brief(
    brief: Brief, tree: SlicingTree, aspect: float | None = None
) -> Brief:
    """A brief whose footprint is solved, or whose programme is scaled to fit.

    The one call that turns a programme and a parcel into something the engine
    can generate from without being hand-calibrated first. Solve the footprint
    if the parcel can hold the brief; otherwise build on the whole parcel and
    scale the programme down, which is the honest answer to a site that is too
    small — every room loses the same fraction.

    The solved footprint is then *placed* by `place_footprint`. That is not a
    refinement: a building floating in the middle of its parcel has no frontage
    on the street, so L5 cannot find a front door and every candidate is refused
    as unreachable. Solving the size without settling where it stands would have
    made fitted briefs *less* buildable than hand-calibrated ones.
    """
    try:
        solved = fit_footprint(
            brief.programme, brief.parcel, brief.profile, tree, aspect
        )
        placed = place_footprint(solved, brief.parcel)
        footprint = placed if placed.buildable(brief.parcel) else solved
    except InfeasibleBrief:
        footprint = Footprint.of_parcel(brief.parcel)
        programme = fit_programme(
            brief.programme, footprint, brief.parcel, brief.profile, tree
        )
        return replace(
            brief,
            programme=programme,
            footprint=footprint,
            budget=check_feasibility(programme, brief.parcel, brief.profile),
        )
    return replace(brief, footprint=footprint)


# --- internals --------------------------------------------------------------


def _brief(
    programme: Programme,
    parcel: Parcel,
    profile: RegulationProfile,
    footprint: Footprint,
) -> Brief:
    """A brief built without the feasibility gate.

    `Brief.load` refuses an infeasible programme; the solver has to be able to
    measure one, since measuring is how it discovers the parcel is too small.
    """
    return Brief(
        programme=programme,
        parcel=parcel,
        profile=profile,
        budget=check_feasibility(programme, parcel, profile),
        footprint=footprint,
    )


def _grid(footprint: Footprint):
    """The structural grid of a footprint. Local import: `partition` imports
    `brief`, so a module-level import here would close the cycle."""
    from planfgen.partition.grid import StructuralGrid

    return StructuralGrid.from_span(
        footprint.w, footprint.h, origin=(footprint.x, footprint.y)
    )


def _bracket(shortfall, demand: float) -> tuple[float, float, float]:
    """(lo, hi, shortfall(hi)) with lo undershooting and hi overshooting.

    A footprint too small for the tree's own walls raises rather than returning
    a number; that is an undershoot, and the cleanest lower bound there is.
    """
    lo = demand * BRACKET_LOW
    hi = demand * BRACKET_HIGH
    for _ in range(BRACKET_TRIES):
        try:
            f_hi = shortfall(hi)
        except ValueError:
            lo, hi = hi, hi * BRACKET_GROW
            continue
        if f_hi > 0:
            return lo, hi, f_hi
        lo, hi = hi, hi * BRACKET_GROW
    raise ValueError(
        f"no footprint under {hi:.1f} m2 delivers the {demand:.2f} m2 demanded; "
        f"the tree is probably spending everything on walls"
    )


def _budget_for(
    programme: Programme,
    parcel: Parcel,
    profile: RegulationProfile,
    tree: SlicingTree,
    demand: float,
):
    """The area budget that explains why a solved footprint will not fit.

    Charged against the largest footprint the parcel can hold — its bounding
    box — so the deficit reported is the real one rather than the estimate
    `check_feasibility` makes before any tree exists.
    """
    from planfgen.brief.feasibility import AreaBudget

    whole = Footprint.of_parcel(parcel)
    interior = parcel.interior(profile.facade_t)
    try:
        habitable = delivered(whole, programme, parcel, profile, tree)
    except ValueError:
        habitable = 0.0
    return AreaBudget(
        gross=parcel.outline.area,
        interior=interior.area if not interior.is_empty else 0.0,
        partition_estimate=estimate_partition_length(
            len(programme.rooms), interior.area if not interior.is_empty else 0.0
        ),
        habitable=habitable,
        required=demand,
        deficit=demand - habitable,
    )
