"""L1 — what the rooms owe each other, before any geometry exists.

v1 had one kind of relation: an untyped pair, meaning roughly "these should be
near each other". That is not enough to build from. A kitchen next to a bathroom
wants a shared *wet wall* and no door; a bedroom off a corridor wants a door; a
WC opposite a kitchen wants neither. Those are three different requirements and
only one of them is satisfied by putting the rooms close together.

So relations are typed, and the type says what the later layers have to deliver:
`CONNECTED` becomes a door-capable run of shared wall, `ADJACENT` a shared wall
with no door, `NEAR` a short path, and `SEPARATED` an instruction not to touch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

import networkx as nx

from planfgen.brief.programme import Programme


class RelationType(Enum):
    """What a relation demands of the plan."""

    CONNECTED = "connected"
    ADJACENT = "adjacent"
    NEAR = "near"
    SEPARATED = "separated"

    @property
    def needs_wall(self) -> bool:
        """True if the two rooms must share a run of wall."""
        return self in (RelationType.CONNECTED, RelationType.ADJACENT)

    @property
    def needs_door(self) -> bool:
        """True if that run must be long enough to host a door leaf and jambs."""
        return self is RelationType.CONNECTED

    @property
    def forbids_wall(self) -> bool:
        """True if the two rooms must not touch at all."""
        return self is RelationType.SEPARATED


@dataclass(frozen=True)
class Relation:
    """One typed requirement between two rooms.

    Symmetric, so the two names are stored in a canonical order — a relation
    written either way round is the same relation.
    """

    a: str
    b: str
    kind: RelationType
    weight: float = 1.0

    def __post_init__(self) -> None:
        if self.a == self.b:
            raise ValueError(f"a room cannot be related to itself: {self.a!r}")
        if self.b < self.a:
            low, high = self.b, self.a
            object.__setattr__(self, "a", low)
            object.__setattr__(self, "b", high)

    @property
    def pair(self) -> tuple[str, str]:
        return (self.a, self.b)

    def other(self, nom: str) -> str:
        """The room at the far end. Raises KeyError if `nom` is not in it."""
        if nom == self.a:
            return self.b
        if nom == self.b:
            return self.a
        raise KeyError(f"{nom!r} is not part of {self.pair}")

    def to_json(self) -> dict:
        return {"a": self.a, "b": self.b, "kind": self.kind.name, "weight": self.weight}

    @classmethod
    def from_json(cls, entry) -> Relation:
        """One relation, from either the v2 object form or a bare v1 pair."""
        if isinstance(entry, dict):
            return cls(
                a=entry["a"],
                b=entry["b"],
                kind=RelationType[entry["kind"]],
                weight=float(entry.get("weight", 1.0)),
            )
        a, b = entry
        return cls(a=a, b=b, kind=RelationType.CONNECTED)


@dataclass(frozen=True)
class ProgrammeGraph:
    """Every relation in the brief, as one graph."""

    relations: list[Relation] = field(default_factory=list)

    def neighbours(
        self, nom: str, kinds: Iterable[RelationType] | RelationType | None = None
    ) -> list[str]:
        """Rooms related to this one, optionally filtered by relation kind."""
        wanted = _as_kinds(kinds)
        return sorted(
            {
                relation.other(nom)
                for relation in self.relations
                if nom in relation.pair and (wanted is None or relation.kind in wanted)
            }
        )

    def of_kind(self, kinds: Iterable[RelationType] | RelationType) -> list[Relation]:
        """Every relation of the given kind or kinds, in order."""
        wanted = _as_kinds(kinds)
        return [r for r in self.relations if r.kind in wanted]

    def between(self, a: str, b: str) -> Relation | None:
        """The relation joining these two rooms, if there is one."""
        pair = tuple(sorted((a, b)))
        for relation in self.relations:
            if relation.pair == pair:
                return relation
        return None

    @property
    def noms(self) -> list[str]:
        """Every room mentioned by any relation."""
        return sorted({nom for relation in self.relations for nom in relation.pair})

    def to_networkx(self) -> nx.Graph:
        """The graph as NetworkX, with kind and weight on every edge."""
        graph = nx.Graph()
        graph.add_nodes_from(self.noms)
        for relation in self.relations:
            graph.add_edge(
                relation.a, relation.b, kind=relation.kind, weight=relation.weight
            )
        return graph

    def validate(self, programme: Programme) -> list[str]:
        """Names the relations mention that the programme does not contain."""
        known = {room.nom for room in programme.rooms}
        return sorted({nom for nom in self.noms if nom not in known})

    def to_json(self) -> list[dict]:
        return [relation.to_json() for relation in self.relations]

    @classmethod
    def from_json(cls, entries: list) -> ProgrammeGraph:
        """Load a relation list.

        Accepts the v1 untyped pair format — `[["Séjour", "Cuisine"], ...]` —
        and promotes every pair to `CONNECTED`, which is what v1 meant by an
        adjacency even though it had no way to say so. Old fixtures still load.
        """
        return cls(relations=[Relation.from_json(entry) for entry in entries])


def _as_kinds(
    kinds: Iterable[RelationType] | RelationType | None,
) -> frozenset[RelationType] | None:
    if kinds is None:
        return None
    if isinstance(kinds, RelationType):
        return frozenset({kinds})
    return frozenset(kinds)
