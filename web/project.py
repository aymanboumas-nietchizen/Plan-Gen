"""The project the studio edits: a building, its storeys, the flats on each.

    Projet ─ parcelle, profil réglementaire
      └─ Niveaux (RDC, étage courant ×n, attique)
           └─ Plateau : noyau + palier (à venir, S19), logements
                └─ Logement type (A, B… : F2/F3/F4) ─ pièces

A flat is designed once as a *type* and placed on as many storeys as the mix
says, as an agency does (« logement type A »). Each type has a **slot** — its
frontage and depth on the plate — and is generated inside that slot, not on the
whole lot: an F3 asked to fill an 11 x 13 m lot was refused 6 seeds of 6, the
same F3 on its own 9 x 11 m slot passes (measured 2026-09-29). A slot is bounded
by its neighbours, so its side edges are blind (MITOYEN); its front and back are
the lot's.

The unit level is the only one the engine generates today. The storey level
lays the slots side by side along the street and reports what is left for the
core; the building level sums the storeys. Both are arithmetic, and say so.
Nothing here holds a regulation value: a plate's core and common circulation
will come from `brief/regulation.py` when the engine has a floor plate.

The document is plain JSON so the page can keep it, save it and send it back.
"""

from __future__ import annotations

from collections import Counter

from web import engine

SCHEMA = "planfgen.project/1"

STOREY_KINDS: dict[str, str] = {
    "RDC": "Rez-de-chaussée",
    "COURANT": "Étage courant",
    "ATTIQUE": "Attique",
}

#: Said wherever the page would otherwise imply the engine composes a plate.
PLATE_PENDING = (
    "Le moteur ne compose pas encore un plateau (noyau, palier, 2 à 4 logements) : "
    "c'est l'étape S19. Chaque logement type est généré seul, dans sa trame."
)


def new_unit(uid: str, label: str, typology: str) -> dict:
    """A unit type from a preset: its programme, its relations, its slot."""
    preset = engine.meta()["presets"][typology]
    return {
        "id": uid,
        "label": label,
        "typology": typology,
        "slot": {"width": preset["width"], "depth": preset["depth"]},
        "rooms": preset["rooms"],
        "relations": preset["relations"],
        "chosen": None,
    }


def default_project() -> dict:
    """An R+2 between party walls, two flats a storey: what the agency builds."""
    return {
        "schema": SCHEMA,
        "name": "Immeuble R+2",
        "profile": "economique",
        "lot": {
            "width": 24.0,
            "depth": 14.0,
            "north": 0.0,
            "edges": ["STREET", "MITOYEN", "COURT", "MITOYEN"],
            "entry_edge": 0,
        },
        "storeys": [
            {"id": "rdc", "kind": "RDC", "label": "RDC", "repeat": 1,
             "slots": [{"unit": "B"}]},
            {"id": "ec", "kind": "COURANT", "label": "Étage courant", "repeat": 2,
             "slots": [{"unit": "A"}, {"unit": "B"}]},
        ],
        "units": [new_unit("A", "Type A", "F3"), new_unit("B", "Type B", "F4")],
    }


def _unit(project: dict, uid: str) -> dict:
    for unit in project.get("units") or []:
        if unit.get("id") == uid:
            return unit
    raise engine.BriefError(f"Logement type inconnu : {uid!r}.")


def unit_spec(project: dict, uid: str) -> dict:
    """The brief one flat is generated from: its slot, the lot's front and back
    edges and north, the project's profile, the unit's programme.

    The page composes the same object (`unitSpec` in app.js); a test holds the
    two to the same fields.
    """
    unit = _unit(project, uid)
    lot = project.get("lot") or {}
    slot = unit.get("slot") or {}
    edges = list(lot.get("edges") or ["STREET", "MITOYEN", "COURT", "MITOYEN"])
    entry = int(lot.get("entry_edge", 0))
    return {
        "typology": unit.get("typology", uid),
        "profile": project.get("profile"),
        "width": slot.get("width", lot.get("width")),
        "depth": slot.get("depth", lot.get("depth")),
        "north": lot.get("north", 0.0),
        "edges": [edges[0], "MITOYEN", edges[2], "MITOYEN"],
        "entry_edge": entry if entry in (0, 2) else 0,
        "rooms": unit.get("rooms") or [],
        "relations": unit.get("relations") or [],
    }


def _utile(unit: dict) -> float:
    return sum(float(r.get("surface") or 0.0) for r in unit.get("rooms") or [])


def summary(project: dict) -> dict:
    """The building in numbers: storeys, flats, frontage and surface, per storey.

    Arithmetic over what was asked, not over generated plans. A storey whose
    slots are wider than the lot cannot be built; one that fits leaves `free`
    metres of frontage, which is where the core and landing will have to go —
    whether that is enough needs the floor-plate engine.
    """
    if not isinstance(project, dict):
        raise engine.BriefError("Le projet doit être un objet JSON.")
    lot = project.get("lot") or {}
    try:
        width, depth = float(lot["width"]), float(lot["depth"])
    except (KeyError, TypeError, ValueError):
        raise engine.BriefError("La parcelle du projet n'a pas de dimensions.") from None
    gross = width * depth
    units = {u.get("id"): u for u in project.get("units") or []}

    storeys, count, levels, total = [], Counter(), 0, 0.0
    for storey in project.get("storeys") or []:
        repeat = int(storey.get("repeat") or 1)
        if repeat < 1:
            raise engine.BriefError(f"« {storey.get('label')} » : il faut au moins un niveau.")
        placed = []
        for slot in storey.get("slots") or []:
            unit = units.get(slot.get("unit"))
            if unit is None:
                raise engine.BriefError(
                    f"« {storey.get('label')} » place un logement type inconnu : {slot.get('unit')!r}."
                )
            frame = unit.get("slot") or {"width": width, "depth": depth}
            placed.append(
                {
                    "unit": unit["id"],
                    "label": unit.get("label"),
                    "typology": unit.get("typology"),
                    "utile": round(_utile(unit), 2),
                    "slot": [float(frame["width"]), float(frame["depth"])],
                }
            )
            count[unit.get("typology")] += repeat
        utile = sum(p["utile"] for p in placed)
        frontage = sum(p["slot"][0] for p in placed)
        too_deep = [p["label"] for p in placed if p["slot"][1] > depth + 1e-9]
        storeys.append(
            {
                "id": storey.get("id"),
                "label": storey.get("label"),
                "kind": storey.get("kind"),
                "repeat": repeat,
                "units": placed,
                "utile": round(utile, 2),
                "frontage": round(frontage, 2),
                "free": round(width - frontage, 2),
                "too_deep": too_deep,
                "fits": frontage <= width + 1e-9 and not too_deep,
            }
        )
        levels += repeat
        total += utile * repeat

    return {
        "name": project.get("name"),
        "levels": levels,
        "height": f"R+{levels - 1}" if levels else "—",
        "lot": round(gross, 2),
        "lot_dims": [width, depth],
        "storeys": storeys,
        "logements": sum(count.values()),
        "mix": dict(sorted(count.items())),
        "utile": round(total, 2),
        "plate": PLATE_PENDING,
    }
