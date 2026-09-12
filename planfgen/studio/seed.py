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

WHAT DOES HAVE TO BE SAID BEFORE GENERATING is the consequence, because the
studio's standard is that a brief which cannot be built is explained before
anything is run. A band's area is an *output* — it absorbs whatever the envelope
has left over. With no band, the rooms absorb it instead: every one of them
overshoots its target by the same fraction, and `AREA_TOLERANCE` refuses the lot.
Measured 2026-08-28 on the studio's own sidebar defaults — 12 x 10 m, edges
STREET / MITOYEN / COURT / MITOYEN, four seeds, 200 iterations, the default
programme scaled:

    programme    slack over required    plans found
      92.5 m2         12.6 %             0 of 4    <- the default, corridor deleted
      98.0 m2          6.3 %             0 of 4
     100.0 m2          4.2 %             4 of 4
     101.8 m2          2.3 %             4 of 4
     104.1 m2          0.0 %             4 of 4

The 5 % gate falls inside that gap, so the slack the budget already knows is a
usable prediction — but `AreaBudget.habitable` is a deliberately optimistic
estimate (see `brief/feasibility.py`), so it is a warning here and never a
refusal. The gate stays the engine's to enforce.

The one thing this module does refuse is a programme with fewer than two rooms
beside the circulation: one room is not a partition, it is the envelope, and no
envelope changes that.
"""

from __future__ import annotations

from dataclasses import dataclass

from planfgen.brief import AreaBudget, Programme
from planfgen.evaluate import AREA_TOLERANCE
from planfgen.partition import BandCut, Cut, Direction, Leaf, SlicingTree

#: The fewest rooms beside the circulation that can be cut into a plan.
MIN_ROOMS = 2


@dataclass(frozen=True)
class SpineNote:
    """What the studio is about to seed, and what the user is told about it.

    `kind` is one of:

    - ``"band"``   — a circulation room names the spine; the normal case.
    - ``"open"``   — no circulation room, and the programme fills its envelope.
    - ``"tight"``  — no circulation room, and nothing absorbs the parcel's slack.
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
    rooms = [r.nom for r in programme.rooms if not r.kind.is_circulation]
    if len(rooms) < MIN_ROOMS:
        return SpineNote(
            "refused",
            f"Il faut au moins {MIN_ROOMS} pieces hors circulation pour couper "
            f"un plan ; le programme en compte {len(rooms)}. Une piece unique "
            f"n'est pas une partition, c'est l'enveloppe. Rien n'est genere.",
        )

    if programme.circulation_rooms:
        noms = ", ".join(r.nom for r in programme.circulation_rooms)
        return SpineNote(
            "band",
            f"Spine : bande de circulation nommee par {noms}. Sa largeur est une "
            f"donnee, sa surface un resultat : c'est elle qui absorbe la marge.",
        )

    slack = -budget.deficit
    overshoot = slack / budget.required if budget.required > 0 else 0.0
    head = (
        "Aucune piece de circulation : le plan sera coupe sans couloir, les "
        "pieces ouvrant les unes sur les autres. C'est un plan reel (un F1 ou "
        "un F2 en a rarement un), mais aucune bande n'absorbe alors la marge : "
        f"les {slack:.2f} m2 se repartissent sur les pieces, soit environ "
        f"{overshoot:.1%} d'ecart de surface."
    )
    if overshoot > AREA_TOLERANCE:
        return SpineNote(
            "tight",
            f"{head} La porte 'surface' refuse au-dela de {AREA_TOLERANCE:.0%} : "
            f"montez les surfaces d'environ {overshoot:.0%}, ou ajoutez une "
            f"ligne de circulation (COULOIR).",
        )
    return SpineNote(
        "open", f"{head} C'est sous la tolerance de {AREA_TOLERANCE:.0%}."
    )


def seed_tree(programme: Programme) -> SlicingTree:
    """A spine with the rooms hung off it, half on each side.

    The spine is a `BandCut` — a corridor, width from the profile, area an
    output — only when the programme has a circulation room left to name it.
    Otherwise it is a plain `Cut` and the rooms open into one another.
    """
    rooms = [r.nom for r in programme.rooms if not r.kind.is_circulation]
    if len(rooms) < MIN_ROOMS:
        raise ValueError(
            f"a plan needs at least {MIN_ROOMS} rooms beside the circulation; "
            f"this programme has {len(rooms)}"
        )
    half = max(1, len(rooms) // 2)
    halves = (_chain(rooms[:half]), _chain(rooms[half:]))
    if programme.circulation_rooms:
        return SlicingTree(BandCut(Direction.V, halves))
    return SlicingTree(Cut(Direction.V, False, halves))


def _chain(noms: list[str]) -> Leaf | Cut:
    """The rooms of one half, stacked."""
    node: Leaf | Cut = Leaf(noms[-1])
    for nom in reversed(noms[:-1]):
        node = Cut(Direction.H, False, (Leaf(nom), node))
    return node
