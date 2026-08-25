"""Mutations on the slicing tree, and on where the building stands.

Trees are frozen and stay frozen through the search: a move rebuilds the path
from the root to the node it changes and shares everything else, so a rejected
candidate costs nothing to throw away and the accepted one cannot be corrupted
by the next mutation. Briefs are frozen too, and the two footprint moves at the
bottom of this file work the same way — they return a new `Brief`.

**What is not here is a positional move on a cut.** ARCHITECTURE section 6 lists
`slide_cut` among the mutations, but with exact sizing a cut has no position of
its own to slide: the split is wherever the demanded areas put it, and adding a
displacement to a cut is undone by the refinement pass on the very next
iteration — measured, not assumed. What is left is the one thing that genuinely
moves a cut, which is putting it on the structural grid and letting the areas
either side absorb the difference. That is what `slide_cut` does.

The building itself *does* have a position, and since S14 it has a size that is
not simply the parcel. `slide_footprint` and `shape_footprint` are how the
search argues with `place_footprint`, which is only a rule.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace

from planfgen.brief.footprint import (
    Footprint,
    fit_footprint,
    place_footprint,
)
from planfgen.brief.plan import Brief, InfeasibleBrief
from planfgen.partition.grid import StructuralGrid
from planfgen.partition.tree import (
    BandCut,
    Cut,
    Direction,
    Leaf,
    Node,
    SlicingTree,
)


#: Largest slide, as a fraction of the room the building has to move in.
SLIDE_STEP = 0.35

#: Below this much freedom, in metres, there is nowhere to slide to.
SLIDE_TOL = 1e-9

#: Largest change of proportion, in natural log units. 0.25 is about a quarter
#: wider or narrower.
SHAPE_STEP = 0.25


def _walk(node: Node) -> list[Node]:
    """Every node, pre-order."""
    if isinstance(node, Leaf):
        return [node]
    out = [node]
    for child in node.children:
        out.extend(_walk(child))
    return out


def _at(node: Node, target: int, fn, counter: list[int]) -> Node:
    """Rebuild the tree with `fn` applied to the node at pre-order `target`."""
    index = counter[0]
    counter[0] += 1
    if index == target:
        return fn(node)
    if isinstance(node, Leaf):
        return node
    children = tuple(_at(child, target, fn, counter) for child in node.children)
    return replace(node, children=children)


def _apply(tree: SlicingTree, target: int, fn) -> SlicingTree:
    return SlicingTree(root=_at(tree.root, target, fn, [0]))


def _pick(rng: random.Random, nodes: list[int]) -> int | None:
    return rng.choice(nodes) if nodes else None


def _indices(tree: SlicingTree, kind) -> list[int]:
    return [i for i, node in enumerate(_walk(tree.root)) if isinstance(node, kind)]


def _cut_indices(tree: SlicingTree) -> list[int]:
    """Binary cuts only — a band's direction is `rotate_band`'s business."""
    return [
        i
        for i, node in enumerate(_walk(tree.root))
        if isinstance(node, Cut) and not isinstance(node, BandCut)
    ]


# --- the moves --------------------------------------------------------------


def swap_leaves(tree: SlicingTree, rng: random.Random) -> SlicingTree:
    """Exchange two rooms' positions in the tree. The commonest useful move."""
    leaves = _indices(tree, Leaf)
    if len(leaves) < 2:
        return tree
    first, second = rng.sample(leaves, 2)
    noms = {i: _walk(tree.root)[i].nom for i in (first, second)}
    moved = _apply(tree, first, lambda node: Leaf(noms[second]))
    return _apply(moved, second, lambda node: Leaf(noms[first]))


def flip_cut(tree: SlicingTree, rng: random.Random) -> SlicingTree:
    """Turn one binary cut through ninety degrees."""
    target = _pick(rng, _cut_indices(tree))
    if target is None:
        return tree
    return _apply(
        tree,
        target,
        lambda node: replace(node, direction=_other(node.direction)),
    )


def slide_cut(
    tree: SlicingTree, rng: random.Random, grid: StructuralGrid | None = None
) -> SlicingTree:
    """Move a cut onto the structural grid, or take it off again.

    The only move that changes where a cut lands. A free cut sits wherever the
    areas demand; make it structural and it snaps to the nearest grid line,
    carries a bearing wall instead of a cloison, and the rooms either side
    absorb the difference. `grid` is accepted for signature stability — the
    snapping itself happens in `realise`, which already holds the grid.
    """
    target = _pick(rng, _cut_indices(tree))
    if target is None:
        return tree
    return _apply(tree, target, lambda node: replace(node, structural=not node.structural))


def rotate_band(tree: SlicingTree, rng: random.Random) -> SlicingTree:
    """Turn a spine from a vertical run into a horizontal one, or back."""
    target = _pick(rng, _indices(tree, BandCut))
    if target is None:
        return tree
    return _apply(
        tree,
        target,
        lambda node: replace(node, direction=_other(node.direction)),
    )


def insert_band(tree: SlicingTree, rng: random.Random, budget: int = 0) -> SlicingTree:
    """Turn a binary cut into a corridor band.

    The move the search was missing. Nothing else creates circulation, so a
    seed with one spine could only ever be rearranged into another plan with
    one spine — and past about eight rooms one spine cannot both reach every
    room and leave any of them a decent shape. Measured before this existed:
    the ceiling sat at eight rooms however long the run.

    `budget` is how many bands the programme can still name. A band takes its
    name from a circulation room, so proposing more of them than the brief has
    is proposing a plan that cannot be realised.
    """
    if len(tree.bands()) >= budget:
        return tree
    target = _pick(rng, _cut_indices(tree))
    if target is None:
        return tree
    return _apply(
        tree,
        target,
        lambda node: BandCut(direction=node.direction, children=node.children),
    )


def remove_band(tree: SlicingTree, rng: random.Random) -> SlicingTree:
    """Turn a corridor band back into an ordinary cut, freeing its name."""
    bands = _indices(tree, BandCut)
    if len(bands) < 2:
        return tree          # never remove the last one; a plan needs a way in
    target = rng.choice(bands)
    return _apply(
        tree,
        target,
        lambda node: Cut(
            direction=node.direction, structural=False, children=node.children
        ),
    )


def regroup(tree: SlicingTree, rng: random.Random) -> SlicingTree:
    """Lift one room out of the tree and graft it back somewhere else.

    The only move that changes the tree's *shape* rather than its labels, so it
    is the one that can turn a chain into a pair of wings.
    """
    leaves = [node.nom for node in _walk(tree.root) if isinstance(node, Leaf)]
    if len(leaves) < 3:
        return tree

    nom = rng.choice(leaves)
    pruned = _drop(tree.root, nom, [False])
    if pruned is None:
        return tree

    hosts = list(range(len(_walk(pruned))))
    target = rng.choice(hosts)
    direction = rng.choice(list(Direction))
    first = rng.random() < 0.5

    def graft(node: Node) -> Node:
        pair = (Leaf(nom), node) if first else (node, Leaf(nom))
        return Cut(direction=direction, structural=False, children=pair)

    return SlicingTree(root=_at(pruned, target, graft, [0]))


def _drop(node: Node, nom: str, done: list[bool]) -> Node | None:
    """The tree without the first leaf named `nom`; cuts left with one child
    collapse into it."""
    if isinstance(node, Leaf):
        if node.nom == nom and not done[0]:
            done[0] = True
            return None
        return node
    kept = [child for child in (_drop(c, nom, done) for c in node.children) if child]
    if not kept:
        return None
    if len(kept) == 1:
        return kept[0]
    return replace(node, children=tuple(kept))


def _other(direction: Direction) -> Direction:
    return Direction.H if direction is Direction.V else Direction.V


#: Every move, for the annealer to draw from.
MOVES = (swap_leaves, flip_cut, slide_cut, rotate_band, regroup,
         insert_band, remove_band)


def mutate(
    tree: SlicingTree,
    rng: random.Random,
    grid: StructuralGrid | None = None,
    band_budget: int = 1,
) -> SlicingTree:
    """One random move.

    `slide_cut` wants the grid; `insert_band` wants to know how many bands the
    programme can name, since a band takes its name from a circulation room.
    """
    move = rng.choice(MOVES)
    if move is slide_cut:
        return slide_cut(tree, rng, grid)
    if move is insert_band:
        return insert_band(tree, rng, band_budget)
    return move(tree, rng)

# --- and where the building stands ------------------------------------------
#
# These take a `Brief` rather than a tree, because a footprint is part of the
# brief. They are no-ops on a brief that has none: such a brief builds on its
# whole parcel, and quietly giving it a smaller building would change what was
# asked for rather than how it is arranged.


def slide_footprint(brief: Brief, rng: random.Random) -> Brief:
    """Move the building within what may be built on, without resizing it.

    A local step rather than a redraw. Where a building sits changes which
    rooms face the street, how far the entry is from the boundary, and — once
    parcels stop being rectangles — whether it fits at all. `place_footprint`
    has an opinion about all of that; this is what lets the search hold a
    different one.
    """
    footprint = brief.footprint
    if footprint is None:
        return brief
    try:
        lox, loy, hix, hiy = brief.parcel.buildable_bounds()
    except ValueError:
        return brief

    free_x = (hix - lox) - footprint.w
    free_y = (hiy - loy) - footprint.h
    if free_x <= SLIDE_TOL and free_y <= SLIDE_TOL:
        return brief                      # the building fills its site

    def step(low: float, free: float, at: float) -> float:
        if free <= SLIDE_TOL:
            return low
        moved = at + rng.uniform(-SLIDE_STEP, SLIDE_STEP) * free
        return min(max(moved, low), low + free)

    return replace(
        brief,
        footprint=replace(
            footprint,
            x=step(lox, free_x, footprint.x),
            y=step(loy, free_y, footprint.y),
        ),
    )


def shape_footprint(
    brief: Brief, rng: random.Random, tree: SlicingTree | None = None
) -> Brief:
    """Trade the building's width against its depth at constant *delivered* area.

    Constant delivered area, not constant footprint area — those are different
    things, and the difference is the point. A longer, thinner building has more
    facade, so it spends more of itself on wall and hands its rooms less. Nudging
    the proportion and keeping the gross area would quietly shrink every room;
    so the move re-solves instead, which costs a `fit_footprint` and is why the
    annealer proposes it only some of the time.

    The step is multiplicative, so widening and narrowing are the same size of
    move — an aspect is a ratio, and stepping it by a constant would not be.
    """
    footprint = brief.footprint
    if footprint is None or tree is None:
        return brief
    aspect = footprint.aspect * math.exp(rng.uniform(-SHAPE_STEP, SHAPE_STEP))
    try:
        solved = fit_footprint(
            brief.programme, brief.parcel, brief.profile, tree, aspect
        )
    except (ValueError, InfeasibleBrief):
        return brief                      # that proportion does not fit; keep this one
    placed = place_footprint(solved, brief.parcel)
    return replace(
        brief, footprint=placed if placed.buildable(brief.parcel) else solved
    )


#: Every move on the brief, for the annealer to draw from.
BRIEF_MOVES = (slide_footprint, shape_footprint)


def mutate_brief(
    brief: Brief, tree: SlicingTree, rng: random.Random
) -> Brief:
    """One random move on where and how the building sits."""
    move = rng.choice(BRIEF_MOVES)
    if move is shape_footprint:
        return shape_footprint(brief, rng, tree)
    return move(brief, rng)
