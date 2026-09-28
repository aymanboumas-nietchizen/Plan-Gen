"""Studio — the tree a typed programme gets, and what has to be said first.

`seed_tree` used to sit in `app.py`, where nothing headless could reach it:
Streamlit's `AppTest` has no `data_editor` element, so the one input that breaks
it — the programme table with the `Couloir` row deleted — cannot be produced by
a test that drives the page. It is a function with a return value here so that
the studio's answer to a corridorless programme is testable without a browser.

THE ANSWER, decided 2026-08-28: a corridorless programme gets a PLAN, not a
refusal. A `BandCut` is a corridor, and a corridor has to be *named* by a
circulation room in the programme, so a band with no name is a tree no envelope
can realise — `UnrealisableTree`, raised by `check_nameable` before any geometry.
But the plan itself is perfectly legitimate. An F1 or an F2 genuinely has no
corridor; its rooms open into one another. The engine builds one: on the studio's
own default programme, corridorless and sized to fill its envelope, 4 of 4 seeds
found a plan (measured 2026-08-28).

WHAT HAD TO BE SAID BEFORE GENERATING, UNTIL 2026-09-27: that with no band the
rooms absorbed the parcel's slack, overshot together, and met the 5 % area gate.
That was true only because the studio built on the whole parcel. It now solves
the footprint first (`pipeline.fit`), so the building is sized to what the
leaves ask for and the slack stays unbuilt, band or no band. The `tight` note
went with it; so did the band note's claim that the corridor absorbs the margin
— a band has a fixed width, so it never could.

The one thing this module does refuse is a programme with fewer than two rooms
beside the circulation: one room is not a partition, it is the envelope, and no
envelope changes that.
"""

from __future__ import annotations

from dataclasses import dataclass

from planfgen.brief import AreaBudget, Programme
from planfgen.brief.programme import RoomType
from planfgen.partition import BandCut, Cut, Direction, Leaf, SlicingTree

#: The fewest rooms beside the circulation that can be cut into a plan.
MIN_ROOMS = 2


@dataclass(frozen=True)
class SpineNote:
    """What the studio is about to seed, and what the user is told about it.

    `kind` is one of:

    - ``"band"``   — a circulation room names the spine; the normal case.
    - ``"open"``   — no circulation room: rooms open into one another.
    - ``"refused"``— too few rooms to cut; nothing is generated.
    """

    kind: str
    message: str

    @property
    def ok(self) -> bool:
        """False when the studio should stop before generating anything."""
        return self.kind != "refused"

    @property
    def banded(self) -> bool:
        """True when the spine will be a corridor rather than a plain cut."""
        return self.kind == "band"


def spine_note(programme: Programme, budget: AreaBudget) -> SpineNote:
    """What `seed_tree` will do with this programme, in French, before it does it."""
    rooms = [r.nom for r in programme.rooms if not r.kind.names_band]
    if len(rooms) < MIN_ROOMS:
        return SpineNote(
            "refused",
            f"Il faut au moins {MIN_ROOMS} pieces hors circulation pour couper "
            f"un plan ; le programme en compte {len(rooms)}. Une piece unique "
            f"n'est pas une partition, c'est l'enveloppe. Rien n'est genere.",
        )

    if programme.band_rooms:
        noms = ", ".join(r.nom for r in programme.band_rooms)
        return SpineNote(
            "band",
            f"Spine : bande de circulation nommee par {noms}. Sa largeur est une "
            f"donnee, sa surface un resultat. L'emprise est calculee pour le "
            f"programme ; le reste de la parcelle n'est pas bati.",
        )

    return SpineNote(
        "open",
        "Aucun couloir : le plan sera coupe sans bande de circulation, les "
        "pieces ouvrant les unes sur les autres. C'est un plan reel (un F1 ou "
        "un F2 en a rarement un).",
    )


def seed_tree(programme: Programme) -> SlicingTree:
    """A spine with the rooms hung off it, half on each side.

    The spine is a `BandCut` — a corridor, width from the profile, area an
    output — only when the programme has a circulation room left to name it.
    Otherwise it is a plain `Cut` and the rooms open into one another.
    """
    rooms = [r.nom for r in programme.rooms if not r.kind.names_band]
    if len(rooms) < MIN_ROOMS:
        raise ValueError(
            f"a plan needs at least {MIN_ROOMS} rooms beside the circulation; "
            f"this programme has {len(rooms)}"
        )
    half = max(1, len(rooms) // 2)
    halves = (_chain(rooms[:half]), _chain(rooms[half:]))
    if programme.band_rooms:
        return SlicingTree(BandCut(Direction.V, halves))
    return SlicingTree(Cut(Direction.V, False, halves))


def _chain(noms: list[str], direction: Direction = Direction.H) -> Leaf | Cut:
    """The rooms of one half, stacked."""
    node: Leaf | Cut = Leaf(noms[-1])
    for nom in reversed(noms[:-1]):
        node = Cut(direction, False, (Leaf(nom), node))
    return node


#: The rooms of the day zone. Everything else that is not a corridor sleeps,
#: washes or stores, and goes behind.
DAY_ROOMS = frozenset({RoomType.SEJOUR, RoomType.CUISINE, RoomType.ENTREE})


def zoned_tree(programme: Programme) -> SlicingTree | None:
    """Day zone along the street, night zone behind, the corridor serving it.

    The parti of nearly every Moroccan flat, and measured to matter
    (2026-09-28, `tools/probe_programmes.py`): between two party walls the
    building is as wide as the lot, and the plain spine of `seed_tree` then
    cuts sides 5-6 m deep, which leaves an 11 m2 bedroom 2.3 m wide. The F4
    preset went from 0 of 4 plans to 4 of 4 on this seed.

    The root cut is horizontal, so the day row is the one on the entry edge
    when the street is at the bottom of the drawing, which is how the studio
    draws it; on any other entry the search moves it. The night rooms are
    split between the corridor's two sides by area, largest first.

    None when there is no day zone, or too little night to cut into two sides.
    """
    rooms = [r for r in programme.rooms if not r.kind.names_band]
    day = [r.nom for r in rooms if r.kind in DAY_ROOMS]
    night = sorted(
        (r for r in rooms if r.kind not in DAY_ROOMS),
        key=lambda r: -r.surface_utile,
    )
    if not day or len(night) < 2:
        return None
    sides: tuple[list[str], list[str]] = ([], [])
    areas = [0.0, 0.0]
    for room in night:
        i = 0 if areas[0] <= areas[1] else 1
        sides[i].append(room.nom)
        areas[i] += room.surface_utile
    halves = (_chain(sides[0]), _chain(sides[1]))
    spine = (
        BandCut(Direction.V, halves)
        if programme.band_rooms
        else Cut(Direction.V, False, halves)
    )
    return SlicingTree(Cut(Direction.H, False, (_chain(day, Direction.V), spine)))


def seed_trees(programme: Programme) -> list[SlicingTree]:
    """Every seed worth starting from, the preferred first.

    The caller fits each and keeps the one nearest to passing; on a tie the
    earlier wins, which is why the zoned parti leads.
    """
    zoned = zoned_tree(programme)
    return ([zoned] if zoned is not None else []) + [seed_tree(programme)]
