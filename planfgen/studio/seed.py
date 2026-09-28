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


def _chain(noms: list[str]) -> Leaf | Cut:
    """The rooms of one half, stacked."""
    node: Leaf | Cut = Leaf(noms[-1])
    for nom in reversed(noms[:-1]):
        node = Cut(Direction.H, False, (Leaf(nom), node))
    return node
