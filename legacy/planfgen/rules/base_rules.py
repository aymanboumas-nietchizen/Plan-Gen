"""
rules/base_rules.py
===================
Generic rule framework for layout validation.

Rules are applied AFTER generate_layout() and BEFORE score_layout().

Rules come in two flavours:
  - hard (hard=True)  : failing layout is discarded entirely by the optimizer
  - soft (hard=False) : failure adds a score_penalty (0.05 per violation)

This separation is intentional:
  - Hard rules protect regulatory compliance (non-negotiable)
  - Soft rules guide quality (architect can adjust weights/thresholds)
  - The generator stays simple — it knows nothing about rules
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List

from planfgen.core.geometry import Room, Envelope


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class RuleResult:
    """Outcome of a single rule check against a single room (or the layout)."""
    ok: bool
    rule_name: str
    room: str     # nom of the room this applies to, or "" for layout-wide rules
    message: str
    severity: str  # "error" (hard) | "warning" (soft)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class Rule(ABC):
    """Abstract base for all PLANFGEN rules."""

    name: str = "BaseRule"
    hard: bool = True   # True → hard (elimination), False → soft (penalty)

    @abstractmethod
    def check(self, placed, wall_system=None) -> List[RuleResult]:
        """
        Evaluate the rule against a fully placed layout.

        Returns a list of RuleResult — one per violation found.
        Returns an empty list if the rule passes.
        """
        ...


# ---------------------------------------------------------------------------
# Concrete rules
# ---------------------------------------------------------------------------

class MinAreaRule(Rule):
    """
    Room area must be >= min_area (in m²).

    room_type is matched against room noms using case-insensitive partial
    matching — e.g. "chambre" matches "Chambre 1", "chambre principale".
    """

    def __init__(self, room_type: str, min_area: float, hard: bool = True):
        self.name      = f"MinArea({room_type}>={min_area}m²)"
        self.hard      = hard
        self.room_type = room_type.lower()
        self.min_area  = min_area

    def check(self, placed, wall_system=None) -> List[RuleResult]:
        results = []
        severity = "error" if self.hard else "warning"
        for nom, rect in placed.items():
            if self.room_type in nom.lower():
                if rect.area < self.min_area:
                    results.append(RuleResult(
                        ok=False,
                        rule_name=self.name,
                        room=nom,
                        message=(
                            f"{nom}: area={rect.area:.2f}m² < required {self.min_area}m²"
                        ),
                        severity=severity,
                    ))
        return results


class MaxRatioRule(Rule):
    """
    Room elongation ratio (max/min side) must not exceed max_ratio.
    Applies to ALL rooms unless room_types is specified.
    """

    def __init__(self, max_ratio: float = 2.5, hard: bool = False, room_types: list = None):
        self.name       = f"MaxRatio(<={max_ratio})"
        self.hard       = hard
        self.max_ratio  = max_ratio
        self.room_types = [rt.lower() for rt in (room_types or [])]

    def check(self, placed, wall_system=None) -> List[RuleResult]:
        results = []
        severity = "error" if self.hard else "warning"
        for nom, rect in placed.items():
            if self.room_types and not any(rt in nom.lower() for rt in self.room_types):
                continue
            if rect.ratio > self.max_ratio:
                results.append(RuleResult(
                    ok=False,
                    rule_name=self.name,
                    room=nom,
                    message=(
                        f"{nom}: ratio={rect.ratio:.2f} > max {self.max_ratio} "
                        f"(w={rect.w:.2f}, h={rect.h:.2f})"
                    ),
                    severity=severity,
                ))
        return results


class MinCorridorWidthRule(Rule):
    """
    Rooms matching "couloir" or "corridor" must have min(w, h) >= 1.20 m.
    Required by Moroccan DTU building code.
    """

    MIN_WIDTH = 1.20
    TYPES = ("couloir", "corridor", "hall", "dégagement")

    def __init__(self, hard: bool = True):
        self.name = f"MinCorridorWidth(>={self.MIN_WIDTH}m)"
        self.hard = hard

    def check(self, placed, wall_system=None) -> List[RuleResult]:
        results = []
        severity = "error" if self.hard else "warning"
        for nom, rect in placed.items():
            if any(t in nom.lower() for t in self.TYPES):
                if min(rect.w, rect.h) < self.MIN_WIDTH:
                    results.append(RuleResult(
                        ok=False,
                        rule_name=self.name,
                        room=nom,
                        message=(
                            f"{nom}: min side={min(rect.w, rect.h):.2f}m "
                            f"< required {self.MIN_WIDTH}m"
                        ),
                        severity=severity,
                    ))
        return results


class MinWidthRule(Rule):
    """
    Room minimum width check — shortest side of the minimum rotated rectangle
    must be >= min_width (in metres).

    Uses Shapely's minimum_rotated_rectangle for accurate width estimation
    on any polygon shape (rectangles, Voronoi cells, L-shapes, etc.).
    """

    def __init__(self, room_type: str, min_width: float, hard: bool = False):
        self.name      = f"MinWidth({room_type}>={min_width}m)"
        self.hard      = hard
        self.room_type = room_type.lower()
        self.min_width = min_width

    def check(self, placed, wall_system=None) -> List[RuleResult]:
        from shapely.geometry import Point as ShapelyPoint
        results = []
        severity = "error" if self.hard else "warning"
        for nom, room in placed.items():
            if self.room_type in nom.lower():
                mrr = room.polygon.minimum_rotated_rectangle
                coords = list(mrr.exterior.coords)
                d1 = ShapelyPoint(coords[0]).distance(ShapelyPoint(coords[1]))
                d2 = ShapelyPoint(coords[1]).distance(ShapelyPoint(coords[2]))
                actual_min = min(d1, d2)
                if actual_min < self.min_width:
                    results.append(RuleResult(
                        ok=False,
                        rule_name=self.name,
                        room=nom,
                        message=(
                            f"{nom}: min width={actual_min:.2f}m "
                            f"< required {self.min_width}m"
                        ),
                        severity=severity,
                    ))
        return results


class FacadeRule(Rule):
    """
    Rooms of specified types must touch an exterior wall (facade access).
    This is a soft rule by default — it penalises the score but does not
    eliminate the layout.
    """

    def __init__(self, room_types: List[str], hard: bool = False):
        self.name       = f"FacadeAccess({', '.join(room_types)})"
        self.hard       = hard
        self.room_types = [rt.lower() for rt in room_types]
        # W and H are stored lazily per call — injected via validate_layout
        self._W: float = 0.0
        self._H: float = 0.0

    def check(self, placed, wall_system=None) -> List[RuleResult]:
        # _envelope preferred; fall back to _W/_H for backward compat
        results = []
        severity = "error" if self.hard else "warning"
        for nom, rect in placed.items():
            if any(rt in nom.lower() for rt in self.room_types):
                envelope = getattr(self, "_envelope", None)
                if envelope is not None:
                    on_facade = rect.on_facade(envelope)
                else:
                    on_facade = rect.on_facade(self._W, self._H)
                if not on_facade:
                    results.append(RuleResult(
                        ok=False,
                        rule_name=self.name,
                        room=nom,
                        message=f"{nom}: no facade access (required for this room type)",
                        severity=severity,
                    ))
        return results


# ---------------------------------------------------------------------------
# Validation runner
# ---------------------------------------------------------------------------

_SOFT_PENALTY_PER_VIOLATION = 0.05


def validate_layout(
    placed: Dict[str, Room],
    rules: List[Rule],
    W: float = 0.0,
    H: float = 0.0,
    envelope=None,
    wall_system=None,
) -> dict:
    """
    Run all rules against a layout.

    Parameters
    ----------
    placed      : {nom: Room} layout dict
    rules       : list of Rule objects to run
    W, H        : envelope dimensions (backward compat — prefer passing envelope)
    envelope    : Envelope object (preferred over W/H)
    wall_system : WallSystem for access rules (Sprint 7)

    Returns
    -------
    {
        "valid":         bool,           # False if any hard rule fails
        "errors":        [RuleResult],   # hard failures
        "warnings":      [RuleResult],   # soft failures
        "score_penalty": float,          # cumulative soft penalty (capped at 1.0)
    }
    """
    errors:   List[RuleResult] = []
    warnings: List[RuleResult] = []

    for rule in rules:
        # Inject envelope dims into FacadeRule (backward compat + Envelope)
        if isinstance(rule, FacadeRule):
            rule._W = W
            rule._H = H
            if envelope is not None:
                rule._envelope = envelope
        # All rules accept wall_system=None via the ABC signature
        rule_results = rule.check(placed, wall_system=wall_system)
        for r in rule_results:
            if not r.ok:
                if r.severity == "error":
                    errors.append(r)
                else:
                    warnings.append(r)

    score_penalty = min(len(warnings) * _SOFT_PENALTY_PER_VIOLATION, 1.0)

    return {
        "valid":         len(errors) == 0,
        "errors":        errors,
        "warnings":      warnings,
        "score_penalty": round(score_penalty, 4),
    }
