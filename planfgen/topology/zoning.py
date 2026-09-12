"""L1 — grouping the programme before anything is cut.

Two groupings matter to the layers below. The **wet cluster** is the set of rooms
that need plumbing, and L4 wants them on as few stacks as possible, so they had
better not end up at opposite corners. The **day / night / service** split is the
oldest rule in residential planning and the one that decides whether a flat is
comfortable: you do not want the kitchen between two bedrooms.

`suggest_tree_order` is what replaces v1's BFS placement. v1 walked the
adjacency graph and *placed rectangles as it went*, which is why the graph
survived and the geometry did not. This orders leaves, and stops. What the order
means geometrically is L2's business.
"""

from __future__ import annotations

from planfgen.brief.programme import Programme, RoomType
from planfgen.topology.relations import ProgrammeGraph, RelationType

#: How much a relation of each kind pulls two rooms together in the ordering.
#: SEPARATED pushes, and pushes harder than CONNECTED pulls, so a forbidden
#: pair is not merely un-preferred but actively driven apart.
AFFINITY: dict[RelationType, float] = {
    RelationType.CONNECTED: 2.0,
    RelationType.ADJACENT: 1.5,
    RelationType.NEAR: 0.5,
    RelationType.SEPARATED: -3.0,
}

#: Added when two blocks belong to the same day/night/service group.
ZONE_BONUS = 0.75

#: Which group each room type keeps. A judgement call, and the conventional
#: French one: the salle de bain sits with the chambres because it serves them,
#: while the WC is a service room reachable from the day side.
_DAY = frozenset({RoomType.SEJOUR, RoomType.CUISINE, RoomType.BUREAU, RoomType.TERRASSE})
_NIGHT = frozenset({RoomType.CHAMBRE, RoomType.CHAMBRE_PRINCIPALE, RoomType.SDB})
_SERVICE = frozenset({RoomType.WC, RoomType.CELLIER, RoomType.COULOIR, RoomType.ENTREE})


def wet_cluster(programme: Programme) -> list[str]:
    """Rooms that need plumbing, in programme order.

    L4 assigns stack ids to these. Keeping them contiguous in the tree order is
    the cheapest thing L1 can do to make that possible.
    """
    return [room.nom for room in programme.rooms if room.kind.is_wet]


def day_night(programme: Programme) -> dict[str, str]:
    """Each room as "day", "night" or "service"."""
    groups = {}
    for room in programme.rooms:
        if room.kind in _DAY:
            groups[room.nom] = "day"
        elif room.kind in _NIGHT:
            groups[room.nom] = "night"
        elif room.kind in _SERVICE:
            groups[room.nom] = "service"
        else:
            groups[room.nom] = "service"
    return groups


def suggest_tree_order(graph: ProgrammeGraph, programme: Programme) -> list[str]:
    """A leaf order in which related and like-zoned rooms sit close together.

    The wet cluster is treated as a single block while the chain is built and
    expanded afterwards, so it comes out contiguous by construction rather than
    by luck. Everything else is a greedy chain on affinity, with every tie
    broken by name so the same brief always gives the same order.
    """
    noms = [room.nom for room in programme.rooms]
    wet = wet_cluster(programme)
    zones = day_night(programme)

    blocks: list[list[str]] = [[nom] for nom in noms if nom not in set(wet)]
    if wet:
        blocks.append(list(wet))
    if not blocks:
        return []

    ordered_blocks = _chain(blocks, graph, zones)
    return [
        nom
        for block in ordered_blocks
        for nom in (block if len(block) == 1 else _chain_members(block, graph, zones))
    ]


def _affinity(x: list[str], y: list[str], graph: ProgrammeGraph, zones) -> float:
    score = 0.0
    for a in x:
        for b in y:
            relation = graph.between(a, b)
            if relation is not None:
                score += AFFINITY[relation.kind] * relation.weight
    if _zone_of(x, zones) == _zone_of(y, zones):
        score += ZONE_BONUS
    return score


def _zone_of(block: list[str], zones: dict[str, str]) -> str:
    """The group a block belongs to: whichever its members mostly share."""
    counts: dict[str, int] = {}
    for nom in block:
        group = zones.get(nom, "service")
        counts[group] = counts.get(group, 0) + 1
    return max(sorted(counts), key=lambda group: counts[group])


def _chain(blocks: list[list[str]], graph: ProgrammeGraph, zones) -> list[list[str]]:
    """Greedy nearest-affinity chain over blocks, deterministic throughout.

    The chain is seeded from the *least* connected block, because a chain has
    two ends and starting in the middle wastes one of them: seeded from the hub
    of a star, every spoke after the first lands next to a spoke it has nothing
    to do with. Starting at an extremity lets the chain run through the hub.

    `remaining` is kept sorted by name and `max` returns the first maximal
    element, so every tie breaks to the alphabetically earlier room and the
    same brief always yields the same order.
    """
    remaining = sorted(blocks, key=lambda block: block[0])
    totals = [
        sum(_affinity(b, o, graph, zones) for j, o in enumerate(remaining) if i != j)
        for i, b in enumerate(remaining)
    ]
    ordered = [remaining.pop(min(range(len(remaining)), key=lambda i: totals[i]))]

    while remaining:
        tail = ordered[-1]
        placed = [nom for block in ordered for nom in block]
        best = max(
            range(len(remaining)),
            key=lambda i: (
                _affinity(tail, remaining[i], graph, zones),
                _affinity(placed, remaining[i], graph, zones),
            ),
        )
        ordered.append(remaining.pop(best))
    return ordered


def _chain_members(block: list[str], graph: ProgrammeGraph, zones) -> list[str]:
    return [nom for group in _chain([[n] for n in block], graph, zones) for nom in group]
