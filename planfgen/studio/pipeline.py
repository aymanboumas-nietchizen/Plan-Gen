"""Studio — one generation, from a typed brief to everything the page draws.

It used to be the bottom half of `app.py`, inline, which is how the studio came
to skip `fit_brief` without any test noticing: the page built on the whole
parcel, the band has a fixed width and cannot absorb the slack, so every room
overshot its target and the area gate refused every real programme
(`tools/probe_ceiling.py` and `tools/probe_programmes.py`, 2026-09-27). The
studio only ever worked on a demo programme sized to fill its 12 x 10 m parcel.

Now the footprint is solved first. The building is sized to the programme and
placed on the lot; what the parcel has left over stays unbuilt. A function with
a return value, so the page's generation is testable without a browser.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from planfgen.brief import Brief
from planfgen.brief.footprint import Footprint, fit_brief
from planfgen.brief.regulation import (
    MA_CASABLANCA,
    MA_ECONOMIQUE,
    MA_PROFILE,
    RegulationProfile,
)
from planfgen.fabric.plan import FabricPlan
from planfgen.openings import place_openings
from planfgen.openings.place import OpeningReport
from planfgen.partition import SlicingTree
from planfgen.search import Result, RunStats, anneal, grid_for
from planfgen.services import assign_stack_ids, assign_wet_walls, place_shafts
from planfgen.services.stacking import Level
from planfgen.studio.seed import seed_tree
from planfgen.topology import ProgrammeGraph

#: The selector's choices, sourced profiles first. The key is what the page
#: shows; the placeholder is last and says what it is.
PROFILE_CHOICES: dict[str, RegulationProfile] = {
    "Habitat economique — decret 2-64-445": MA_ECONOMIQUE,
    "Casablanca — arrete municipal": MA_CASABLANCA,
    "Provisoire — valeurs non sourcees": MA_PROFILE,
}

#: Storey height handed to the stacking pass. One level, so it only labels.
STOREY_HEIGHT = 2.80


@dataclass(frozen=True)
class Fitting:
    """The brief the engine will generate from, and what fitting it did."""

    brief: Brief
    footprint: Footprint
    scaled: float | None
    note: str

    @property
    def shrunk(self) -> bool:
        """True when the lot was too small and every room lost area."""
        return self.scaled is not None and self.scaled < 1.0


@dataclass(frozen=True)
class Generation:
    """One run, and everything derived from its best plan."""

    fitting: Fitting
    result: Result | None
    stats: RunStats
    fabric: FabricPlan | None = None
    shafts: tuple = ()
    openings: OpeningReport | None = None

    @property
    def ok(self) -> bool:
        return self.result is not None


def fit(brief: Brief, tree: SlicingTree) -> Fitting:
    """Size the building to the programme and place it on the lot.

    `fit_brief` has two outcomes and the page must tell them apart: a footprint
    smaller than the lot (the normal case), or the whole lot with every room
    scaled down because the lot is too small. A tree that cannot be fitted at
    all falls back to building on the whole parcel, and says so.
    """
    try:
        fitted = fit_brief(brief, tree)
    except ValueError as exc:
        footprint = Footprint.of_parcel(brief.parcel)
        return Fitting(
            replace(brief, footprint=footprint), footprint, None,
            f"Emprise non resolue ({exc}). Le plan occupe toute la parcelle.",
        )

    footprint = fitted.footprint
    asked = brief.programme.total_utile
    got = fitted.programme.total_utile
    scaled = got / asked if asked > 0 and abs(got - asked) > 1e-6 else None
    lot = brief.parcel.outline.area
    head = (
        f"Emprise {footprint.w:.2f} x {footprint.h:.2f} m "
        f"({footprint.w * footprint.h:.1f} m2 sur {lot:.1f} m2 de parcelle)"
    )
    if scaled is not None and scaled < 1.0:
        note = (
            f"{head}. La parcelle est trop petite pour le programme : chaque "
            f"piece est reduite de {1 - scaled:.1%}."
        )
    else:
        note = f"{head}. Le reste de la parcelle n'est pas bati."
    return Fitting(fitted, footprint, scaled, note)


def generate(
    brief: Brief,
    graph: ProgrammeGraph,
    seed: int,
    iterations: int,
) -> Generation:
    """Fit, search, and dress the best plan with services and openings."""
    tree = seed_tree(brief.programme)
    fitting = fit(brief, tree)
    stats = RunStats()
    best = anneal(fitting.brief, tree, iterations, seed=seed, graph=graph, stats=stats)
    if not best:
        return Generation(fitting, None, stats)

    result = best[0]
    profile = result.brief.profile
    fabric = result.plan.to_fabric(profile)
    shafts = place_shafts(fabric, profile)
    assign_wet_walls(fabric, shafts)
    assign_stack_ids(Level(0, STOREY_HEIGHT, fabric, shafts), grid_for(result.brief))
    openings = place_openings(fabric, _Topology(graph), profile, result.brief.programme)
    return Generation(fitting, result, stats, fabric, tuple(shafts), openings)


@dataclass(frozen=True)
class _Topology:
    """What `place_openings` reads off a topology: only its graph."""

    graph: ProgrammeGraph
