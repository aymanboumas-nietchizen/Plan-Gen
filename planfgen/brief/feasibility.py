"""L0 — the feasibility gate: can this programme fit this parcel at all?

Before any partition exists there is no exact internal wall length, so the gate
uses the estimate calibrated in ARCHITECTURE §3. It is deliberately optimistic:
on the 7-room fixture it predicts 33.66 m of cloison against 36.47 m measured,
so the habitable area it reports is slightly *high*. Anything it rejects is
therefore certainly infeasible. L2 replaces the estimate with the exact figure
once a slicing tree exists.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from planfgen.brief.parcel import Parcel
from planfgen.brief.programme import Programme
from planfgen.brief.regulation import RegulationProfile

#: Calibrated coefficient of the partition-length estimate. See ARCHITECTURE §3.
PARTITION_K = 1.3


@dataclass(frozen=True)
class AreaBudget:
    """Where the parcel's area goes, and whether what is left is enough.

    All areas in m². `partition_estimate` is the odd one out: it is a *length*
    in m, the estimated internal partition run that `habitable` was charged for.
    """

    gross: float
    interior: float
    partition_estimate: float
    habitable: float
    required: float
    deficit: float

    @property
    def ok(self) -> bool:
        """True if the programme fits. A positive deficit means it does not."""
        return self.deficit <= 0.0

    def explain(self) -> str:
        """One line carrying every number and the verdict."""
        verdict = (
            f"slack {-self.deficit:.2f} m2" if self.ok else f"DEFICIT {self.deficit:.2f} m2"
        )
        return (
            f"gross {self.gross:.2f} m2 -> interior {self.interior:.2f} m2 "
            f"-> habitable {self.habitable:.2f} m2 after ~{self.partition_estimate:.2f} m "
            f"of cloison; programme needs {self.required:.2f} m2 -> {verdict}"
        )


def estimate_partition_length(n_rooms: int, interior_area: float) -> float:
    """Estimated total length of internal partition, in m.

    The partition run of a plan scales with the square root of the number of
    rooms times the area they are cut from; `PARTITION_K` is calibrated against
    the measured fixture (ARCHITECTURE §3).
    """
    return PARTITION_K * math.sqrt(n_rooms * interior_area)


def check_feasibility(
    programme: Programme, parcel: Parcel, profile: RegulationProfile
) -> AreaBudget:
    """Charge the parcel for its façade and its partitions, then compare.

    The programme's circulation rooms are counted in `n_rooms` because they are
    still leaves that have to be cut for, even though their *area* is an output
    of L2 rather than an input.
    """
    interior_poly = parcel.interior(profile.facade_t)
    interior = interior_poly.area if not interior_poly.is_empty else 0.0

    partition_estimate = estimate_partition_length(len(programme.rooms), interior)
    habitable = interior - partition_estimate * profile.cloison_t
    required = programme.total_utile

    return AreaBudget(
        gross=parcel.outline.area,
        interior=interior,
        partition_estimate=partition_estimate,
        habitable=habitable,
        required=required,
        deficit=required - habitable,
    )
