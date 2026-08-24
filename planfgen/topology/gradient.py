"""L1 — the access gradient: how deep into the flat a room sits.

Depth from the entry, counted over relations you can actually walk through.
A room one step from the door is public whatever it is called; a room three
steps in is private whatever it is called. The gradient is what stops the
partition putting a chambre on the street and the sejour at the back.
"""

from __future__ import annotations

from collections import deque
from enum import Enum

from planfgen.topology.relations import ProgrammeGraph, RelationType


class Zone(Enum):
    """How far from the front door a room sits."""

    PUBLIC = "public"
    SEMI = "semi"
    PRIVATE = "private"


#: Depth at which each zone begins. Depth 0 and 1 are public, 2 is semi, and
#: anything deeper is private.
SEMI_DEPTH = 2
PRIVATE_DEPTH = 3


def zone_of(depth: int) -> Zone:
    """The zone a given BFS depth falls in."""
    if depth >= PRIVATE_DEPTH:
        return Zone.PRIVATE
    if depth >= SEMI_DEPTH:
        return Zone.SEMI
    return Zone.PUBLIC


def depths(
    graph: ProgrammeGraph,
    entry_nom: str,
    kinds: tuple[RelationType, ...] = (RelationType.CONNECTED,),
) -> dict[str, int]:
    """BFS depth from the entry over walkable relations only.

    Only `CONNECTED` is walkable by default: an `ADJACENT` pair shares a wet
    wall with no door in it, and walking through it is not an option.
    """
    found = {entry_nom: 0}
    queue = deque([entry_nom])
    while queue:
        current = queue.popleft()
        for neighbour in graph.neighbours(current, kinds):
            if neighbour not in found:
                found[neighbour] = found[current] + 1
                queue.append(neighbour)
    return found


def access_gradient(graph: ProgrammeGraph, entry_nom: str) -> dict[str, Zone]:
    """Every room in the graph, zoned by its depth from the entry.

    A room the entry cannot reach is `PRIVATE` — it is certainly not public,
    and the fact that it is unreachable at all is L5's finding, not L1's.
    """
    reached = depths(graph, entry_nom)
    return {
        nom: zone_of(reached[nom]) if nom in reached else Zone.PRIVATE
        for nom in set(graph.noms) | {entry_nom}
    }
