"""L5 — can you actually get there, and what do you have to walk through?

A gate, not a score. Two questions, both answered by breadth-first search over
door-capable adjacency only — a run of shared wall shorter than the door module
is not a way through, however close the two rooms come.

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
    return min(candidates, key=lambda c: c[:3])[3]


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
    via_circulation = {entry}
    queue = deque([entry])
    while queue:
        current = queue.popleft()
        if current != entry and not circulation[current]:
            continue
        for neighbour in adjacency[current]:
            if neighbour not in via_circulation:
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
