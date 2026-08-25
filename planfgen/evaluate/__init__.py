"""Beside the stack — `evaluate/`: the gates, and the scores.

Hard constraints and soft scores are kept apart on purpose. A candidate passes
the gates or it is discarded; only what is left gets a number.
"""

from planfgen.evaluate.constraints import (
    AREA_GATE,
    AREA_TOLERANCE,
    ASPECT_GATE,
    CIRCULATION_GATE,
    FURNITURE_GATE,
    GATES,
    MIN_AREA_GATE,
    REACHABLE_GATE,
    Gate,
    all_gates,
    fabric_of,
)
from planfgen.evaluate.metrics import Scores, facings, score

__all__ = [
    "AREA_GATE",
    "AREA_TOLERANCE",
    "ASPECT_GATE",
    "CIRCULATION_GATE",
    "FURNITURE_GATE",
    "GATES",
    "Gate",
    "MIN_AREA_GATE",
    "REACHABLE_GATE",
    "Scores",
    "all_gates",
    "fabric_of",
    "facings",
    "score",
]
