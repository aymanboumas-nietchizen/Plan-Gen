"""L5 — `circulation/`: every space reachable from the entry.

Reachability only, so far. The corridor itself is L2's band cut; what lives here
is the question of whether the plan you ended up with can be walked.
"""

from planfgen.circulation.reachable import ReachabilityReport, entry_space, reachable

__all__ = ["ReachabilityReport", "entry_space", "reachable"]
