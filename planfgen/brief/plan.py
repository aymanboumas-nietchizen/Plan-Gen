"""L0 — `Brief`, the contract handed down to L1.

A `Brief` exists only if the programme fits the parcel, the edges are typed and
north is known. Constructing one from a JSON document runs the feasibility gate,
so a brief that cannot be built at any wall thickness never reaches L1.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from planfgen.brief.feasibility import AreaBudget, check_feasibility
from planfgen.brief.parcel import Parcel
from planfgen.brief.programme import Programme
from planfgen.brief.regulation import MA_PROFILE, RegulationProfile


class InfeasibleBrief(Exception):
    """The programme cannot fit the parcel. Carries the budget that proves it."""

    def __init__(self, budget: AreaBudget):
        self.budget = budget
        super().__init__(budget.explain())


@dataclass(frozen=True)
class Brief:
    """Programme, parcel, regulation and the area budget that reconciles them."""

    programme: Programme
    parcel: Parcel
    profile: RegulationProfile
    budget: AreaBudget

    @classmethod
    def load(cls, path: str | Path, profile: RegulationProfile = MA_PROFILE) -> Brief:
        """Read a brief JSON and gate it.

        Raises `InfeasibleBrief`, carrying the `AreaBudget`, if the programme
        does not fit the parcel.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        programme = Programme.from_json(data)
        parcel = Parcel.from_json(data)
        budget = check_feasibility(programme, parcel, profile)
        if not budget.ok:
            raise InfeasibleBrief(budget)
        return cls(programme=programme, parcel=parcel, profile=profile, budget=budget)
