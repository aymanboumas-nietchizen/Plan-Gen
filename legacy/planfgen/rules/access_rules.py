"""
rules/access_rules.py  –  Sprint 7
=====================================
Hard constraints for room accessibility and connectivity.

All rules here return hard=True violations, meaning layouts with any
violation will be discarded by the optimizer (not just penalised).

Rules:
  AccessibilityRule     – every room reachable from entrance via door graph
  NoDeadEndBedroomRule  – bedrooms must connect to a non-bedroom room
  MinDoorClearanceRule  – all interior doors >= min_width clear opening
"""

from __future__ import annotations

import collections
from typing import Dict, List

from planfgen.rules.base_rules import Rule, RuleResult


class AccessibilityRule(Rule):
    """
    Hard rule: every room must be reachable from the entrance door through
    the interior door graph (BFS traversal).

    A room with no door connection to any other room is an isolated dead-end
    and constitutes an invalid layout.
    """
    name = "Accessibility"
    hard = True

    def check(self, placed, wall_system=None) -> List[RuleResult]:
        if wall_system is None:
            return []

        entrance = wall_system.entrance
        if entrance is None:
            # No entrance found: treat all rooms as inaccessible
            return [
                RuleResult(
                    ok=False, rule_name=self.name, room=nom,
                    message="No entrance door — cannot determine reachability",
                    severity="error",
                )
                for nom in placed
            ]

        start_nom = entrance.wall.room_a
        reachable = set(wall_system.reachable_from(start_nom))

        violations = []
        for nom in placed:
            if nom not in reachable:
                violations.append(RuleResult(
                    ok=False, rule_name=self.name, room=nom,
                    message=f"{nom}: not reachable from entrance via any door",
                    severity="error",
                ))
        return violations


class NoDeadEndBedroomRule(Rule):
    """
    Hard rule: rooms matching 'chambre' must have at least one door connecting
    to a non-bedroom room (e.g. couloir, séjour, hall).

    Prevents labyrinthine bedroom-only chains where you must pass through one
    bedroom to reach another.
    """
    name = "NoDeadEndBedroom"
    hard = True

    _BEDROOM_KEYWORDS   = ("chambre",)
    _SEPARATOR_KEYWORDS = ("couloir", "hall", "séjour", "sejour", "entree", "entree")

    def check(self, placed, wall_system=None) -> List[RuleResult]:
        if wall_system is None:
            return []

        door_graph = wall_system.door_graph()
        violations = []

        for nom in placed:
            if not any(kw in nom.lower() for kw in self._BEDROOM_KEYWORDS):
                continue
            neighbors = door_graph.get(nom, [])
            has_non_bedroom = any(
                not any(kw in nb.lower() for kw in self._BEDROOM_KEYWORDS)
                for nb in neighbors if nb
            )
            if not has_non_bedroom:
                violations.append(RuleResult(
                    ok=False, rule_name=self.name, room=nom,
                    message=(
                        f"{nom} only connects to other bedrooms or has no door — "
                        "must connect to a corridor or living space"
                    ),
                    severity="error",
                ))
        return violations


class MinDoorClearanceRule(Rule):
    """
    Hard rule: every interior door must have a clear opening of at least
    min_width metres (default 0.80 m per Moroccan DTU).
    """
    name = "MinDoorClearance"
    hard = True

    def __init__(self, min_width: float = 0.80):
        self.min_width = min_width

    def check(self, placed, wall_system=None) -> List[RuleResult]:
        if wall_system is None:
            return []

        violations = []
        for door in wall_system.doors:
            if door.width < self.min_width:
                violations.append(RuleResult(
                    ok=False, rule_name=self.name,
                    room=door.wall.room_a,
                    message=(
                        f"Door between {door.wall.room_a!r} and {door.wall.room_b!r} "
                        f"is {door.width:.2f} m — minimum is {self.min_width:.2f} m"
                    ),
                    severity="error",
                ))
        return violations


# Convenience list for the optimizer
ACCESS_RULES = [
    AccessibilityRule(),
    NoDeadEndBedroomRule(),
    MinDoorClearanceRule(min_width=0.80),
]