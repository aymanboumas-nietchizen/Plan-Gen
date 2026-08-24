"""Mutations on the slicing tree. Every one returns a new tree.

Trees are frozen and stay frozen through the search: a move rebuilds the path
from the root to the node it changes and shares everything else, so a rejected
candidate costs nothing to throw away and the accepted one cannot be corrupted
by the next mutation.

**What is not here is a positional move.** ARCHITECTURE section 6 lists
`slide_cut` among the mutations, but with exact sizing a cut has no position of
its own to slide: the split is wherever the demanded areas put it, and adding a
displacement to a cut is undone by the refinement pass on the very next
iteration — measured, not assumed. What is left is the one thing that genuinely
moves a cut, which is putting it on the structural grid and letting the areas
either side absorb the difference. That is what `slide_cut` does.
"""

from __future__ import annotations

import random
from dataclasses import replace

from planfgen.partition.grid import StructuralGrid
from planfgen.partition.tree import (
    BandCut,
    Cut,
    Direction,
    Leaf,
    Node,
    SlicingTree,
)


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
MOVES = (swap_leaves, flip_cut, slide_cut, rotate_band, regroup)


def mutate(
    tree: SlicingTree, rng: random.Random, grid: StructuralGrid | None = None
) -> SlicingTree:
    """One random move. `slide_cut` is the only one that wants the grid."""
    move = rng.choice(MOVES)
    if move is slide_cut:
        return slide_cut(tree, rng, grid)
    return move(tree, rng)
