"""L5 — `circulation/`: every space reachable from the entry.

Two questions, not one. `reachable.py` asks whether you can get there;
`shape.py` asks whether the circulation you spent getting there was worth it.
A corridor running the depth of the building and stopping blind against a
facade passes the first and fails the second.
"""

from planfgen.circulation.reachable import (
    PASS_THROUGH,
    ReachabilityReport,
    access_tree,
    entry_space,
    reachable,
)
from planfgen.circulation.shape import (
    CirculationReport,
    Run,
    circulation_runs,
)

__all__ = [
    "CirculationReport",
    "PASS_THROUGH",
    "ReachabilityReport",
    "Run",
    "access_tree",
    "circulation_runs",
    "entry_space",
    "reachable",
]
