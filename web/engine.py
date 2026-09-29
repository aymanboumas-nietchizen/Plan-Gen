"""The web studio's only contact with the engine: a JSON brief in, a JSON option out.

Everything here is a plain function with a return value, so the API is tested
without a server and the worker processes can import it on Windows (spawn).

The brief is assembled the way `planfgen/studio/app.py` assembles it: a
rectangular lot, four typed edges in ring order, a programme and its relations.
It is copied rather than imported because `app.py` runs Streamlit at import.

What the page draws is derived from the same `FabricPlan` the DXF is written
from: the bridge document `to_gh_json` (spaces, wall axes, openings, shafts),
plus the wall solids with their openings cut out, so the drawing on screen is
the one that leaves in the file.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from planfgen.brief import (
    Brief,
    EdgeSpec,
    EdgeType,
    Orientation,
    Parcel,
    Programme,
    RoomSpec,
    RoomType,
    check_feasibility,
)
from planfgen.brief.regulation import PROFILES
from planfgen.document import PALETTE, export_dxf, to_gh_json
from planfgen.studio.pipeline import generate
from planfgen.studio.presets import PRESETS
from planfgen.studio.seed import spine_note
from planfgen.topology import ProgrammeGraph, Relation, RelationType

#: Profile keys as the page shows them, sourced profiles first.
PROFILE_LABELS: dict[str, str] = {
    "economique": "Habitat économique — décret 2-64-445",
    "casablanca": "Casablanca — arrêté municipal",
    "placeholder": "Provisoire — valeurs non sourcées",
}

#: Edge kinds, in French. Keys are `EdgeType` names.
EDGE_LABELS: dict[str, str] = {
    "STREET": "Rue",
    "COURT": "Cour",
    "GARDEN": "Jardin",
    "MITOYEN": "Mitoyen",
    "RETRAIT": "Retrait",
}

ROOM_LABELS: dict[str, str] = {
    "SEJOUR": "Séjour",
    "CHAMBRE": "Chambre",
    "CHAMBRE_PRINCIPALE": "Chambre principale",
    "CUISINE": "Cuisine",
    "SDB": "Salle de bains",
    "WC": "WC",
    "COULOIR": "Couloir",
    "ENTREE": "Entrée",
    "BUREAU": "Bureau",
    "CELLIER": "Cellier",
    "TERRASSE": "Terrasse",
}

#: What each gate refuses, in the architect's words. Keys are gate names.
GATE_LABELS: dict[str, str] = {
    "area": "surfaces hors tolérance",
    "coverage": "emprise non couverte",
    "min_area": "minimum réglementaire non atteint",
    "furniture": "mobilier impossible à placer",
    "circulation": "largeur de circulation insuffisante",
    "reachable": "pièce inaccessible depuis l'entrée",
    "unrealisable": "découpage irréalisable",
}

#: The edges of the rectangular lot, in ring order from the origin.
SIDES = ("bas", "droite", "haut", "gauche")

MAX_OPTIONS = 12
MAX_ITERATIONS = 2000


class BriefError(ValueError):
    """A brief the page sent that the engine cannot take. The message is French."""


# --- the brief ---------------------------------------------------------------


def meta() -> dict:
    """Everything the form needs to render, including every preset in full."""
    presets = {}
    for key, preset in PRESETS.items():
        presets[key] = {
            "label": preset.label,
            "width": preset.width,
            "depth": preset.depth,
            "rooms": [
                {"nom": n, "kind": k, "surface": a, "orientation": o}
                for n, k, a, o in preset.rooms
            ],
            "relations": [
                {"a": a, "b": b, "kind": k, "weight": w}
                for a, b, k, w in preset.relations
            ],
        }
    return {
        "presets": presets,
        "profiles": PROFILE_LABELS,
        "edges": EDGE_LABELS,
        "rooms": ROOM_LABELS,
        "orientations": [o.name for o in Orientation],
        "sides": list(SIDES),
        "palette": {kind.name: colour for kind, colour in PALETTE.items()},
        "gates": GATE_LABELS,
        "max_options": MAX_OPTIONS,
    }


def default_spec(key: str = "F3", profile: str = "economique") -> dict:
    """A complete brief, as the page would send it, for a preset."""
    preset = meta()["presets"][key]
    return {
        "typology": key,
        "profile": profile,
        "width": preset["width"],
        "depth": preset["depth"],
        "north": 0.0,
        "edges": ["STREET", "MITOYEN", "COURT", "MITOYEN"],
        "entry_edge": 0,
        "rooms": preset["rooms"],
        "relations": preset["relations"],
    }


def _number(spec: dict, key: str, low: float, high: float) -> float:
    try:
        value = float(spec[key])
    except (KeyError, TypeError, ValueError):
        raise BriefError(f"« {key} » manque ou n'est pas un nombre.") from None
    if not math.isfinite(value) or not low <= value <= high:
        raise BriefError(f"« {key} » doit être entre {low:g} et {high:g}.")
    return value


def build(spec: dict) -> tuple[Brief, ProgrammeGraph]:
    """The engine's brief and relation graph, from the page's JSON.

    Raises `BriefError` with a French message for anything the page could send
    wrong; the engine's own `ValueError`s are re-raised as one too.
    """
    profile_key = spec.get("profile")
    if profile_key not in PROFILES:
        raise BriefError(f"Profil réglementaire inconnu : {profile_key!r}.")
    profile = PROFILES[profile_key]

    width = _number(spec, "width", 3.0, 200.0)
    depth = _number(spec, "depth", 3.0, 200.0)
    north = math.radians(_number(spec, "north", -360.0, 360.0))

    edges = spec.get("edges") or []
    if len(edges) != 4 or any(e not in EdgeType.__members__ for e in edges):
        raise BriefError("Il faut quatre limites typées : " + ", ".join(EDGE_LABELS) + ".")
    try:
        entry = int(spec.get("entry_edge", 0))
    except (TypeError, ValueError):
        raise BriefError("La limite d'entrée doit être un numéro de côté.") from None

    rooms = []
    seen: set[str] = set()
    for row in spec.get("rooms") or []:
        nom = str(row.get("nom", "")).strip()
        kind = row.get("kind")
        if not nom:
            continue
        if nom in seen:
            raise BriefError(f"Deux pièces s'appellent « {nom} ».")
        if kind not in RoomType.__members__:
            raise BriefError(f"Type de pièce inconnu pour « {nom} » : {kind!r}.")
        try:
            area = float(row.get("surface"))
        except (TypeError, ValueError):
            raise BriefError(f"La surface de « {nom} » n'est pas un nombre.") from None
        if not 0.5 <= area <= 500.0:
            raise BriefError(f"La surface de « {nom} » doit être entre 0,5 et 500 m².")
        pref = row.get("orientation") or ""
        if pref and pref not in Orientation.__members__:
            raise BriefError(f"Orientation inconnue pour « {nom} » : {pref!r}.")
        seen.add(nom)
        rooms.append(
            RoomSpec(
                nom=nom,
                kind=RoomType[kind],
                surface_utile=area,
                couleur=PALETTE.get(RoomType[kind], "#888888"),
                orientation_pref=Orientation[pref] if pref else None,
            )
        )
    if not rooms:
        raise BriefError("Le programme est vide.")

    relations = []
    for row in spec.get("relations") or []:
        a, b, kind = row.get("a"), row.get("b"), row.get("kind")
        if a not in seen or b not in seen:
            continue  # a relation to a deleted room is dropped, not an error
        if kind not in RelationType.__members__:
            raise BriefError(f"Relation inconnue entre « {a} » et « {b} » : {kind!r}.")
        relations.append(Relation(a, b, RelationType[kind], float(row.get("weight", 1.0))))

    try:
        programme = Programme(rooms)
        parcel = Parcel(
            outline=Polygon([(0, 0), (width, 0), (width, depth), (0, depth)]),
            edges=[EdgeSpec(i, EdgeType[e]) for i, e in enumerate(edges)],
            north=north,
            entry_edge=entry,
        )
    except ValueError as exc:
        raise BriefError(_french(str(exc))) from exc

    budget = check_feasibility(programme, parcel, profile)
    return Brief(programme, parcel, profile, budget), ProgrammeGraph(relations)


def _french(message: str) -> str:
    """The engine speaks English in its exceptions; say the common ones in French."""
    if "the entry must be on a STREET or GARDEN edge" in message:
        return "L'entrée doit se faire sur une limite Rue ou Jardin."
    return message


def check(spec: dict) -> dict:
    """What the page says before the button: does the programme fit the lot."""
    brief, _ = build(spec)
    budget = brief.budget
    note = spine_note(brief.programme, budget)
    return {
        "ok": bool(budget.ok and note.ok),
        "budget_ok": bool(budget.ok),
        "gross": round(budget.gross, 2),
        "habitable": round(budget.habitable, 2),
        "required": round(budget.required, 2),
        "slack": round(-budget.deficit, 2),
        "budget": budget.explain(),
        "spine": note.message,
        "spine_kind": note.kind,
    }


def key_of(spec: dict, seed: int, iterations: int) -> str:
    """The same brief, seed and effort are the same plan: that is the cache key."""
    canonical = json.dumps(
        {"spec": spec, "seed": seed, "iterations": iterations},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]


# --- one option ----------------------------------------------------------------


@dataclass(frozen=True)
class Option:
    """One generation, as the page draws it, and the files it can download."""

    payload: dict
    dxf: bytes | None


def run(spec: dict, seed: int, iterations: int) -> Option:
    """Generate one option. Pure: same arguments, same option.

    Runs in a worker process; everything it returns is picklable.
    """
    brief, graph = build(spec)
    started = time.perf_counter()
    generation = generate(brief, graph, seed=seed, iterations=iterations)
    elapsed = time.perf_counter() - started

    stats = generation.stats
    payload: dict = {
        "key": key_of(spec, seed, iterations),
        "seed": seed,
        "iterations": iterations,
        "ok": generation.ok,
        "elapsed": round(elapsed, 2),
        "note": generation.fitting.note if generation.fitting else "",
        "shrunk": bool(generation.fitting and generation.fitting.shrunk),
        "stats": {
            "proposed": stats.proposed,
            "accepted": stats.accepted,
            "rejected_by": dict(stats.rejected_by),
            "explain": stats.explain(),
        },
    }
    if not generation.ok:
        payload["refusal"] = refusal(stats.rejected_by, stats.proposed)
        return Option(payload, None)

    result = generation.result
    fabric = generation.fabric
    fitted = {r.nom: r.surface_utile for r in result.brief.programme.rooms}
    asked = {r.nom: r.surface_utile for r in brief.programme.rooms}
    footprint = generation.fitting.footprint

    rooms = []
    for nom, space in fabric.spaces.items():
        net_w, net_h = space.net_dims()
        target = fitted.get(nom)
        rooms.append(
            {
                "nom": nom,
                "kind": space.kind.name,
                "asked": asked.get(nom),
                "target": target,
                "net": round(space.surface_utile, 2),
                "net_w": round(net_w, 2),
                "net_h": round(net_h, 2),
                "error": (
                    round((space.surface_utile - target) / target, 4)
                    if target and not space.kind.names_band else None
                ),
            }
        )

    document = to_gh_json(fabric, generation.openings, generation.shafts)
    document["solids"] = solids(document)
    document["footprint"] = [footprint.x, footprint.y, footprint.w, footprint.h]

    scores = result.scores.as_dict()
    payload.update(
        {
            "scores": {k: round(v, 4) for k, v in scores.items()},
            "area_error": round(result.plan.max_area_error(result.brief.profile), 4),
            "surface_utile": round(fabric.total_utile, 2),
            "emprise": [round(footprint.w, 2), round(footprint.h, 2)],
            "rooms": rooms,
            "openings": {
                "doors": len(document["openings"]["doors"]),
                "windows": len(document["openings"]["windows"]),
                "errors": [opening_error(e) for e in (generation.openings.errors if generation.openings else [])],
            },
            "document": document,
        }
    )
    return Option(payload, _dxf_bytes(generation))


_OPENING_ERRORS: tuple[tuple[re.Pattern, str], ...] = (
    (
        re.compile(r"^(.+?)~(.+?): ([\d.]+) m of shared wall, under the ([\d.]+) m a door needs$"),
        "Porte {0} – {1} impossible : {2} m de mur commun, il en faut {3} m.",
    ),
    (
        re.compile(r"^(.+?)~(.+?): ([\d.]+) m shared but no single wall to host a door$"),
        "Porte {0} – {1} impossible : {2} m de mur commun, mais sur aucun mur unique.",
    ),
    (
        re.compile(r"^(.+?): needs daylight and has no openable exterior wall$"),
        "{0} : pas de jour — aucune façade ouvrable pour une fenêtre.",
    ),
    (
        re.compile(r"^(.+?)~(.+?): the plan has no such room$"),
        "Relation {0} – {1} : pièce absente du plan.",
    ),
)


def opening_error(message: str) -> str:
    """One `OpeningReport` error, in French when its form is known."""
    for pattern, french in _OPENING_ERRORS:
        match = pattern.match(message)
        if match:
            return french.format(*match.groups())
    return message


def refusal(rejected_by: dict[str, int], proposed: int) -> str:
    """Why nothing passed, in French, worst gate first."""
    if not rejected_by:
        return "Aucun candidat n'a été proposé."
    parts = [
        f"{GATE_LABELS.get(gate, gate)} ({n})"
        for gate, n in sorted(rejected_by.items(), key=lambda kv: -kv[1])
    ]
    return f"Aucun des {proposed} candidats ne passe les contrôles : " + ", ".join(parts) + "."


def _dxf_bytes(generation) -> bytes:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "plan.dxf"
        export_dxf(
            generation.fabric,
            path,
            openings=generation.openings,
            shafts=generation.shafts,
        )
        return path.read_bytes()


def solids(document: dict) -> list[list[list[list[float]]]]:
    """Wall solids with their openings cut out: polygons, each a list of rings
    (exterior first, then holes — a courtyard of walls has one), in metres.

    One union, so corners close and a T-junction reads as one wall. Each solid
    is the wall's axis rectangle grown by half its thickness at both ends, which
    fills the corner square two abutting solids leave empty; the openings are
    then subtracted along the axis. Export only, never in a loop that searches.
    """
    walls = document["walls"]
    pieces = []
    for wall in walls:
        (x0, y0), (x1, y1) = wall["p0"], wall["p1"]
        half = wall["thickness"] / 2
        pieces.append(
            box(min(x0, x1) - half, min(y0, y1) - half, max(x0, x1) + half, max(y0, y1) + half)
        )
    holes = []
    for opening in document["openings"]["doors"] + document["openings"]["windows"]:
        index = opening["wall"]
        if not 0 <= index < len(walls):
            continue
        wall = walls[index]
        (x0, y0), (x1, y1) = wall["p0"], wall["p1"]
        low, high = opening["span"]
        half = wall["thickness"] / 2 + 1e-3
        length = math.hypot(x1 - x0, y1 - y0) or 1.0
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        ax, ay = x0 + ux * low, y0 + uy * low
        bx, by = x0 + ux * high, y0 + uy * high
        holes.append(
            box(min(ax, bx) - abs(uy) * half, min(ay, by) - abs(ux) * half,
                max(ax, bx) + abs(uy) * half, max(ay, by) + abs(ux) * half)
        )
    shape = unary_union(pieces)
    if holes:
        shape = shape.difference(unary_union(holes))
    out = []
    for polygon in getattr(shape, "geoms", [shape]):
        if polygon.is_empty:
            continue
        rings = [polygon.exterior, *polygon.interiors]
        out.append([[[round(x, 4), round(y, 4)] for x, y in ring.coords[:-1]] for ring in rings])
    return out


def worker_count() -> int:
    """Leave one core to the browser and the server."""
    return max(1, min(MAX_OPTIONS, (os.cpu_count() or 2) - 1))


def warm() -> bool:
    """A no-op a fresh worker runs so its imports are paid before the first request."""
    return True
