"""L5 — can you actually get there, and what do you have to walk through?

A gate, not a score. Two questions, both answered by breadth-first search over
door-capable adjacency only — a run of shared wall shorter than the door module
is not a way through, however close the two rooms come. Two circulation spaces
are the exception, and only to each other: a T-junction is an open passage with
no leaf, so they join over `junction_module` (`FabricPlan.opening_run`).

The second question is the one v1 could not ask. ARCHITECTURE section 1: on the
seven-room fixture, Chambre 1's only door-capable neighbours were Chambre 2, the
WC and the SDB. You entered the bedroom through the bathroom. Reporting the plan
"reachable" would have been true and useless; what matters is whether a room can
be reached without walking through somebody else's.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from planfgen.brief.programme import RoomType
from planfgen.fabric.axis import WallKind
from planfgen.fabric.plan import FabricPlan, Space


#: The only rooms that may be entered THROUGH another room, as (room, via)
#: pairs of kinds. Everything else must be reachable over circulation alone.
#:
#: (BUANDERIE, CUISINE): the laundry is either beside the SDB or off the
#: kitchen, on its balcony or loggia — the architect's placement rule of
#: 2026-09-29. One hop only: the room reached this way is not itself passable,
#: and nothing else is relaxed (a WC through the SDB is still refused).
PASS_THROUGH: frozenset[tuple[RoomType, RoomType]] = frozenset({
    (RoomType.BUANDERIE, RoomType.CUISINE),
})


@dataclass(frozen=True)
class ReachabilityReport:
    """What the search found, and whether it is good enough to keep."""

    entry: str
    reached: set[str] = field(default_factory=set)
    unreachable: set[str] = field(default_factory=set)
    through_room: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Nothing stranded, and nothing reachable only through a habitable room."""
        return not self.unreachable and not self.through_room

    def explain(self) -> str:
        """One line, for the report and for failing tests."""
        if self.ok:
            return f"all {len(self.reached)} spaces reachable from {self.entry}"
        parts = []
        if self.unreachable:
            parts.append(f"unreachable: {', '.join(sorted(self.unreachable))}")
        if self.through_room:
            parts.append(
                "only via a habitable room: "
                + ", ".join(f"{k} via {v}" for k, v in sorted(self.through_room.items()))
            )
        return f"entry {self.entry}; " + "; ".join(parts)


def entry_space(fabric: FabricPlan) -> Space:
    """The space you come in through.

    It must present a facade wall to the parcel's entry edge. An `ENTREE` wins
    outright; failing that any circulation space, because a corridor that meets
    the street *is* the hall; failing that the space with the longest frontage.

    A plan whose programme has an ENTREE and does not come in through it has no
    way in either. An entree at the back of the flat, reached from the corridor
    the front door actually opens onto, is a room named after the wrong thing —
    which the F4 preset produced on 2026-09-28 until this said so.
    """
    candidates: list[tuple[int, float, str, Space]] = []
    for space in fabric.spaces.values():
        run = sum(
            wall.length
            for wall in fabric.walls_on_edge(space, fabric.parcel.entry_edge)
            if wall.kind is WallKind.FACADE
        )
        if run <= 0:
            continue
        rank = 0 if space.kind is RoomType.ENTREE else (1 if space.kind.is_circulation else 2)
        candidates.append((rank, -run, space.nom, space))

    if not candidates:
        raise ValueError(
            f"no space presents a facade wall to entry edge "
            f"{fabric.parcel.entry_edge}; the plan has no way in"
        )
    entry = min(candidates, key=lambda c: c[:3])[3]
    halls = sorted(n for n, s in fabric.spaces.items() if s.kind is RoomType.ENTREE)
    if halls and entry.kind is not RoomType.ENTREE:
        raise ValueError(
            f"{', '.join(halls)} has no facade on entry edge "
            f"{fabric.parcel.entry_edge}; the front door would open onto "
            f"{entry.nom}, not the entree"
        )
    return entry


def reachable(fabric: FabricPlan) -> ReachabilityReport:
    """Breadth-first from the entry, over door-capable adjacency only."""
    adjacency = fabric.adjacency_graph()
    entry = entry_space(fabric).nom
    circulation = {
        nom: space.kind.is_circulation for nom, space in fabric.spaces.items()
    }

    parent: dict[str, str | None] = {entry: None}
    queue = deque([entry])
    while queue:
        current = queue.popleft()
        for neighbour in adjacency[current]:
            if neighbour not in parent:
                parent[neighbour] = current
                queue.append(neighbour)

    # The same search again, but refusing to pass *through* a habitable room.
    # The entry itself is always passable — coming in through it is the point.
    # A room reached legally may still lead on to a room `PASS_THROUGH` allows
    # through it; that one is a dead end (not circulation, so never expanded).
    kind = {nom: space.kind for nom, space in fabric.spaces.items()}
    via_circulation = {entry}
    queue = deque([entry])
    while queue:
        current = queue.popleft()
        passable = current == entry or circulation[current]
        for neighbour in adjacency[current]:
            if neighbour in via_circulation:
                continue
            if passable or (kind[neighbour], kind[current]) in PASS_THROUGH:
                via_circulation.add(neighbour)
                queue.append(neighbour)

    through_room: dict[str, str] = {}
    for nom in parent:
        if nom == entry or nom in via_circulation:
            continue
        ancestor = parent[nom]
        while ancestor is not None and ancestor != entry:
            if not circulation[ancestor]:
                through_room[nom] = ancestor
                break
            ancestor = parent[ancestor]

    return ReachabilityReport(
        entry=entry,
        reached=set(parent),
        unreachable=set(fabric.spaces) - set(parent),
        through_room=through_room,
    )


def access_tree(
    fabric: FabricPlan, prefer: set[frozenset[str]] | frozenset = frozenset()
) -> dict[str, str]:
    """Every space reached legally, mapped to the space its door opens from.

    The walk `reachable` proves exists, written down so L6 can hang a door on
    it: breadth-first from the entry over door-capable walls, through
    circulation only (and `PASS_THROUGH`). Among parents at the same depth a
    pair in `prefer` (a door the architect asked for) wins, then a circulation
    space, then the name — so the same plan always gets the same doors. In
    breadth-first order: a parent comes before its children.
    """
    adjacency = fabric.adjacency_graph()
    entry = entry_space(fabric).nom
    kind = {nom: space.kind for nom, space in fabric.spaces.items()}
    tree: dict[str, str] = {}
    depth = {entry: 0}
    frontier = [entry]
    while frontier:
        options: dict[str, list[tuple[bool, bool, str]]] = {}
        for current in frontier:
            passable = current == entry or kind[current].is_circulation
            for other in adjacency[current]:
                if other in depth:
                    continue
                if passable or (kind[other], kind[current]) in PASS_THROUGH:
                    options.setdefault(other, []).append((
                        frozenset((current, other)) not in prefer,
                        not kind[current].is_circulation,
                        current,
                    ))
        frontier = sorted(options)
        for other in frontier:
            tree[other] = min(options[other])[2]
            depth[other] = depth[tree[other]] + 1
    return tree
