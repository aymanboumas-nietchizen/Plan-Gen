"""L1 — `TopologyPlan`: the brief turned into a graph, and nothing more.

Deliberately a deliverable on its own. A typed relation graph with an access
gradient and a day/night split is worth reading before a single wall exists —
it is the drawing an architect would sketch first — and it round-trips through
JSON so it can be reviewed, edited by hand and fed back in.

Note what is *not* here: coordinates. v1's equivalent stage placed rectangles
while it walked the graph, and the geometry it produced never recovered.
"""

from __future__ import annotations

from dataclasses import dataclass

from planfgen.brief.programme import Orientation, Programme, RoomType
from planfgen.topology.gradient import Zone, access_gradient
from planfgen.topology.relations import ProgrammeGraph
from planfgen.topology.zoning import day_night


@dataclass(frozen=True)
class TopologyPlan:
    """Typed relations, an access gradient, and the day/night grouping."""

    programme: Programme
    graph: ProgrammeGraph
    gradient: dict[str, Zone]
    zones: dict[str, str]

    @classmethod
    def build(cls, programme: Programme, graph: ProgrammeGraph, entry_nom: str) -> TopologyPlan:
        """Derive the gradient and the zoning from a programme and its graph."""
        missing = graph.validate(programme)
        if missing:
            raise ValueError(
                f"the relation graph names rooms the programme does not have: "
                f"{', '.join(missing)}"
            )
        if entry_nom not in {room.nom for room in programme.rooms}:
            raise ValueError(f"entry {entry_nom!r} is not in the programme")
        return cls(
            programme=programme,
            graph=graph,
            gradient=access_gradient(graph, entry_nom),
            zones=day_night(programme),
        )

    def rooms_in(self, zone: Zone) -> list[str]:
        """Every room at this depth from the entry, in programme order."""
        return [r.nom for r in self.programme.rooms if self.gradient.get(r.nom) is zone]

    def to_json(self) -> dict:
        return {
            "programme": [
                {
                    "nom": room.nom,
                    "kind": room.kind.name,
                    "surface_utile": room.surface_utile,
                    "couleur": room.couleur,
                    "daylight": room.daylight,
                    "orientation_pref": (
                        room.orientation_pref.name if room.orientation_pref else None
                    ),
                }
                for room in self.programme.rooms
            ],
            "relations": self.graph.to_json(),
            "gradient": {nom: zone.name for nom, zone in self.gradient.items()},
            "zones": dict(self.zones),
        }

    @classmethod
    def from_json(cls, data: dict) -> TopologyPlan:
        return cls(
            programme=Programme.from_json(data),
            graph=ProgrammeGraph.from_json(data["relations"]),
            gradient={nom: Zone[name] for nom, name in data["gradient"].items()},
            zones=dict(data["zones"]),
        )
