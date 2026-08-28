"""Search tests — the moves, the annealer, and whether the metrics move.

The variance test is the one that matters. v1 shipped `couverture`, which
returned exactly 1.0 on all forty seeds, and a `compacite` that spanned 0.9435
to 1.0000 — a quarter of the weight carrying no signal and another sixth
carrying 1.4 points of it. A number that cannot vary is not a metric, and this
file is where that gets caught.

The fixture is a five-room flat plus a spine on 12.00 x 10.00 m, with the room
targets calibrated to what that envelope and that tree actually deliver, so the
seed passes its own gates and the search starts from a real plan.
"""

from __future__ import annotations

import random
import time

import pytest
from shapely.geometry import Polygon

from planfgen.brief import (
    MA_PROFILE,
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
from planfgen.evaluate import (
    AREA_TOLERANCE,
    ASPECT_GATE,
    GATES,
    Scores,
    all_gates,
    score,
)
from planfgen.partition import BandCut, Cut, Direction, Leaf, SlicingTree
from planfgen.search import (
    KEEP_BEST,
    MOVES,
    RunStats,
    anneal,
    envelope_of,
    evaluate,
    flip_cut,
    grid_for,
    insert_band,
    mutate,
    regroup,
    rotate_band,
    slide_cut,
    swap_leaves,
)
from planfgen.topology import ProgrammeGraph, Relation, RelationType as R

P = MA_PROFILE
O = Orientation
W, H = 12.0, 10.0

#: Calibrated against the seed tree: these are what the envelope delivers, so
#: the reference plan is exact and the search has room to move either way.
#: Re-calibrated when furniture gained a max proportion — the old SDB was
#: 4.91 x 2.08, a bathroom five metres long, and the gate was right to refuse it.
TARGETS = {
    "Sejour": 32.13,
    "Cuisine": 13.14,
    "Ch1": 18.69,
    "Ch2": 15.38,
    "SDB": 13.14,
    "Couloir": 8.00,
}
SPEC = [
    ("Sejour", RoomType.SEJOUR, O.S),
    ("Cuisine", RoomType.CUISINE, O.N),
    ("Ch1", RoomType.CHAMBRE_PRINCIPALE, O.N),
    ("Ch2", RoomType.CHAMBRE, O.S),
    ("SDB", RoomType.SDB, O.E),
    ("Couloir", RoomType.COULOIR, None),
]


def apartment_brief() -> Brief:
    programme = Programme(
        [
            RoomSpec(nom, kind, TARGETS[nom], "#888888", orientation_pref=pref)
            for nom, kind, pref in SPEC
        ]
    )
    parcel = Parcel(
        outline=Polygon([(0, 0), (W, 0), (W, H), (0, H)]),
        edges=[
            EdgeSpec(0, EdgeType.STREET),
            EdgeSpec(1, EdgeType.MITOYEN),
            EdgeSpec(2, EdgeType.COURT),
            EdgeSpec(3, EdgeType.MITOYEN),
        ],
        north=0.0,
        entry_edge=0,
    )
    return Brief(programme, parcel, P, check_feasibility(programme, parcel, P))


def apartment_graph() -> ProgrammeGraph:
    return ProgrammeGraph(
        [
            Relation("Couloir", "Sejour", R.CONNECTED, 2.0),
            Relation("Couloir", "Ch1", R.CONNECTED, 2.0),
            Relation("Couloir", "Ch2", R.CONNECTED, 2.0),
            Relation("Couloir", "SDB", R.CONNECTED),
            Relation("Sejour", "Cuisine", R.CONNECTED, 1.5),
            Relation("Cuisine", "SDB", R.ADJACENT, 2.0),
            Relation("SDB", "Sejour", R.SEPARATED),
            Relation("Ch1", "Ch2", R.NEAR, 0.5),
            Relation("Cuisine", "Ch1", R.SEPARATED, 1.5),
            Relation("Sejour", "Ch2", R.CONNECTED, 0.5),
        ]
    )


def seed_tree() -> SlicingTree:
    """A vertical spine, day rooms west, night rooms east."""
    return SlicingTree(
        BandCut(
            Direction.V,
            (
                Cut(Direction.H, False, (Leaf("Sejour"), Leaf("Cuisine"))),
                Cut(
                    Direction.H,
                    False,
                    (Leaf("Ch1"), Cut(Direction.H, False, (Leaf("Ch2"), Leaf("SDB")))),
                ),
            ),
        )
    )


def leaf_noms(tree: SlicingTree) -> list[str]:
    return sorted(leaf.nom for leaf in tree.leaves())


# --- the moves --------------------------------------------------------------


@pytest.mark.parametrize("move", MOVES, ids=lambda m: m.__name__)
def test_every_move_keeps_the_same_rooms(move):
    """A mutation rearranges the programme. It never gains or loses a room."""
    tree = seed_tree()
    before = leaf_noms(tree)

    for seed in range(40):
        rng = random.Random(seed)
        moved = move(tree, rng, grid_for(apartment_brief())) if move is slide_cut else move(tree, rng)
        assert leaf_noms(moved) == before, move.__name__
        assert len(moved.bands()) == len(tree.bands())


@pytest.mark.parametrize("move", MOVES, ids=lambda m: m.__name__)
def test_every_move_leaves_the_original_untouched(move):
    """Trees are immutable during search, so a rejected candidate costs nothing."""
    tree = seed_tree()
    rng = random.Random(1)
    moved = move(tree, rng, grid_for(apartment_brief())) if move is slide_cut else move(tree, rng)
    assert leaf_noms(tree) == leaf_noms(seed_tree())
    assert tree.root == seed_tree().root
    assert isinstance(moved, SlicingTree)


def test_swap_leaves_actually_swaps():
    tree = seed_tree()
    order = [leaf.nom for leaf in tree.leaves()]
    changed = {
        tuple(leaf.nom for leaf in swap_leaves(tree, random.Random(s)).leaves())
        for s in range(20)
    }
    assert tuple(order) not in changed or len(changed) > 1


def test_flip_and_rotate_turn_a_cut_through_ninety_degrees():
    tree = seed_tree()
    assert tree.root.direction is Direction.V
    rotated = rotate_band(tree, random.Random(0))
    assert rotated.root.direction is Direction.H

    directions = {
        _first_cut(flip_cut(tree, random.Random(s))) for s in range(20)
    }
    assert len(directions) > 1


def _first_cut(tree: SlicingTree):
    from planfgen.partition.tree import Cut as _Cut

    for node in _walk(tree.root):
        if isinstance(node, _Cut) and not isinstance(node, BandCut):
            return node.direction
    return None


def _walk(node):
    from planfgen.partition.tree import Leaf as _Leaf

    if isinstance(node, _Leaf):
        return [node]
    out = [node]
    for child in node.children:
        out.extend(_walk(child))
    return out


def test_slide_cut_moves_a_cut_onto_the_grid_and_off_again():
    """The only move that changes where a cut lands — see moves.py on why."""
    tree = seed_tree()
    flags = {
        tuple(
            n.structural
            for n in _walk(slide_cut(tree, random.Random(s), None).root)
            if hasattr(n, "structural")
        )
        for s in range(20)
    }
    assert len(flags) > 1


def test_regroup_changes_the_shape_not_the_contents():
    tree = seed_tree()
    shapes = {str(regroup(tree, random.Random(s)).root) for s in range(20)}
    assert len(shapes) > 1
    for s in range(20):
        assert leaf_noms(regroup(tree, random.Random(s))) == leaf_noms(tree)


def test_mutate_draws_from_every_move():
    tree = seed_tree()
    grid = grid_for(apartment_brief())
    results = {str(mutate(tree, random.Random(s), grid).root) for s in range(60)}
    assert len(results) > 3


# --- the gates and the seed -------------------------------------------------


def test_the_seed_plan_passes_every_gate():
    brief = apartment_brief()
    plan = seed_tree().realise(envelope_of(brief), brief, grid_for(brief))
    passed, failure = all_gates(plan, brief)
    assert passed, failure
    assert plan.max_area_error(P) < 0.01, "the fixture is calibrated to its envelope"


def test_a_failed_gate_discards_the_candidate_rather_than_scoring_it():
    """Hard constraints are never traded off — CLAUDE.md."""
    brief = apartment_brief()
    grid = grid_for(brief)
    # One room asked to be enormous: the areas can no longer be delivered.
    greedy = Programme(
        [
            RoomSpec(
                r.nom,
                r.kind,
                r.surface_utile * (6.0 if r.nom == "SDB" else 1.0),
                r.couleur,
                orientation_pref=r.orientation_pref,
            )
            for r in brief.programme.rooms
        ]
    )
    broken = Brief(greedy, brief.parcel, P, brief.budget)
    assert evaluate(seed_tree(), broken, grid, apartment_graph(), 0) is None


def test_gates_run_cheapest_first():
    assert [g.name for g in GATES][-1] == "reachable", "the one that builds walls"
    assert AREA_TOLERANCE > 0


def test_circulation_shape_is_gated_but_its_size_is_scored():
    """A corridor leading nowhere is waste; how much corridor is a judgement."""
    from planfgen.circulation import circulation_runs
    from planfgen.evaluate.constraints import fabric_of

    assert "circulation" in [g.name for g in GATES]

    brief, graph = apartment_brief(), apartment_graph()
    plan = seed_tree().realise(envelope_of(brief), brief, grid_for(brief))
    report = circulation_runs(fabric_of(plan, brief))

    assert report.runs and report.worst_stub == pytest.approx(0.0, abs=1e-9)
    assert report.dead_ends(MA_PROFILE.corridor_clear) == []
    assert 0.0 < score(plan, brief, graph).circulation < 1.0, "size still scores"


def test_aspect_is_scored_not_gated():
    """CLAUDE.md lists compactness among the judgement calls, not the gates.

    v1 held its 2.5:1 rule as a warning too. Gating it discarded 222 of 500
    candidates on the v1 brief and hid the real reason that brief fails, which
    is furniture. Shape is protected by FURNITURE_GATE instead.
    """
    assert "aspect" not in [g.name for g in GATES]
    assert ASPECT_GATE.name == "aspect", "still available to a caller who wants it"

    brief, graph = apartment_brief(), apartment_graph()
    plan = seed_tree().realise(envelope_of(brief), brief, grid_for(brief))
    assert 0.0 < score(plan, brief, graph).compacite < 1.0, "it carries the signal"


def test_a_slot_passes_the_gates_only_if_the_furniture_fits():
    """The gate that replaced the aspect gate has to actually bite."""
    from planfgen.evaluate.constraints import ASPECT_GATE as AG, FURNITURE_GATE

    brief = apartment_brief()
    plan = seed_tree().realise(envelope_of(brief), brief, grid_for(brief))
    assert FURNITURE_GATE.check(plan, brief)
    assert AG.check(plan, brief)

    # A chambre 2.00 m wide is legal on area and fails on furniture.
    from planfgen.habitability import FURNITURE, fits

    class _Slot:
        def net_dims(self):
            return (2.00, 9.00)

    assert _Slot().net_dims()[0] * _Slot().net_dims()[1] > MA_PROFILE.min_area[
        RoomType.CHAMBRE
    ], "18 m2, well over the 9 m2 minimum"
    assert fits(_Slot(), FURNITURE[RoomType.CHAMBRE]) is False


def test_minimum_width_is_not_gated():
    """v1 held every MinWidthRule soft; the profile still carries the numbers."""
    from planfgen.evaluate.constraints import _minima_ok

    brief = apartment_brief()
    assert MA_PROFILE.min_width[RoomType.SEJOUR] == 3.00

    narrow = SlicingTree(
        BandCut(
            Direction.V,
            (
                Cut(Direction.H, False, (Leaf("Sejour"), Leaf("Cuisine"))),
                Cut(
                    Direction.H,
                    False,
                    (Leaf("Ch1"), Cut(Direction.H, False, (Leaf("Ch2"), Leaf("SDB")))),
                ),
            ),
        )
    )
    plan = narrow.realise(envelope_of(brief), brief, grid_for(brief))
    # _minima_ok now consults min_area alone, so it cannot depend on min_width.
    assert _minima_ok(plan, brief) is True
    for cell in plan.cells:
        kind = brief.programme.by_nom(cell.nom).kind
        if kind in MA_PROFILE.min_area:
            net_w, net_h = cell.net_dims(MA_PROFILE)
            assert net_w * net_h >= MA_PROFILE.min_area[kind]


# --- annealing --------------------------------------------------------------


def test_anneal_is_deterministic_for_a_fixed_seed():
    brief, graph = apartment_brief(), apartment_graph()
    one = anneal(brief, seed_tree(), 60, seed=7, graph=graph)
    two = anneal(brief, seed_tree(), 60, seed=7, graph=graph)

    assert [r.scores.globale for r in one] == [r.scores.globale for r in two]
    assert [str(r.tree.root) for r in one] == [str(r.tree.root) for r in two]


def test_different_seeds_explore_differently():
    brief, graph = apartment_brief(), apartment_graph()
    finals = {
        anneal(brief, seed_tree(), 60, seed=s, graph=graph)[0].scores.globale
        for s in range(8)
    }
    assert len(finals) > 1


def test_anneal_keeps_the_best_and_improves_on_the_seed():
    brief, graph = apartment_brief(), apartment_graph()
    stats = RunStats()
    best = anneal(brief, seed_tree(), 200, seed=3, graph=graph, stats=stats)

    assert 0 < len(best) <= KEEP_BEST
    assert best == sorted(best, key=lambda r: r.cost), "best first"

    start = evaluate(seed_tree(), brief, grid_for(brief), graph, 0)
    assert best[0].scores.globale >= start.scores.globale
    assert stats.proposed == 200
    assert stats.accepted > 0


def test_two_hundred_iterations_finish_well_inside_five_seconds():
    brief, graph = apartment_brief(), apartment_graph()
    start = time.perf_counter()
    anneal(brief, seed_tree(), 200, seed=1, graph=graph)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0, f"{elapsed:.2f}s for 200 iterations"


def test_anneal_with_no_iterations_returns_the_seed():
    brief, graph = apartment_brief(), apartment_graph()
    assert len(anneal(brief, seed_tree(), 0, graph=graph)) == 1


# --- THE VARIANCE TEST ------------------------------------------------------


def test_every_metric_varies():
    """At least fifty annealed candidates, and no metric stuck on fewer than five.

    The candidates are the ones a run *evaluates*, not the ten it keeps. That
    distinction matters and cost a while to find: a good optimiser concentrates,
    so the kept best-of-ten agree with each other on circulation and compacite
    and show only three values between them. That is the optimiser working, not
    a dead metric — and this test is about the metric. Sampling what the search
    walks over answers the question that was being asked.
    """
    brief, graph = apartment_brief(), apartment_graph()
    grid = grid_for(brief)

    # Several independent walks, not one. A single walk samples one corner of
    # the space, and which corner depends on the move set — adding a move
    # changed the draw order and the answer with it, which is a property of the
    # walk and not of any metric.
    results = []
    for seed in range(6):
        rng = random.Random(seed)
        tree = seed_tree()
        for step in range(1200):
            tree = mutate(tree, rng, grid)
            candidate = evaluate(tree, brief, grid, graph, step)
            if candidate is not None:
                results.append(candidate)
            elif rng.random() < 0.25:
                tree = seed_tree()

    # Every candidate found, not a slice of them. Taking a fixed-stride sample
    # makes the result depend on which stride: fifty saw five orientations here
    # and eighty saw four, which is luck rather than a property of anything.
    assert len(results) >= 50, "the fixture must leave the search room to move"
    seen: dict[str, set[float]] = {k: set() for k in results[0].scores.as_dict()}
    for result in results:
        for name, value in result.scores.as_dict().items():
            seen[name].add(round(value, 9))

    for name, values in seen.items():
        assert len(values) >= 5, f"{name} took only {sorted(values)}"


def test_the_kept_results_still_move():
    """The best-of-ten converge, but they are not all one plan either."""
    brief, graph = apartment_brief(), apartment_graph()
    kept = []
    for seed in range(10):
        kept.extend(anneal(brief, seed_tree(), 60, seed=seed, graph=graph))
    kept = kept[:50]

    globales = {round(r.scores.globale, 9) for r in kept}
    assert len(globales) >= 5, sorted(globales)


def test_compacite_is_not_saturated_by_the_aspect_gate():
    """The trap v1 fell into: a metric whose range a gate already guarantees.

    Scoring `min(1, 2.5 / ratio)` would be exactly 1.0 for every plan the aspect
    gate lets through. The reference is a square instead, so the number moves.
    """
    brief, graph = apartment_brief(), apartment_graph()
    plan = seed_tree().realise(envelope_of(brief), brief, grid_for(brief))
    scores = score(plan, brief, graph)

    assert isinstance(scores, Scores)
    assert 0.0 < scores.compacite < 1.0


def test_scores_are_weighted_to_one():
    from planfgen.evaluate.metrics import (
        W_ADJACENCES,
        W_CIRCULATION,
        W_COMPACITE,
        W_ORIENTATION,
    )

    assert W_ADJACENCES + W_ORIENTATION + W_CIRCULATION + W_COMPACITE == pytest.approx(1.0)

    brief, graph = apartment_brief(), apartment_graph()
    plan = seed_tree().realise(envelope_of(brief), brief, grid_for(brief))
    s = score(plan, brief, graph)
    assert s.globale == pytest.approx(
        W_ADJACENCES * s.adjacences
        + W_ORIENTATION * s.orientation
        + W_CIRCULATION * s.circulation
        + W_COMPACITE * s.compacite
    )


def test_there_is_no_couverture():
    """It returned 1.0 on all forty v1 seeds. It is not coming back."""
    brief = apartment_brief()
    plan = seed_tree().realise(envelope_of(brief), brief, grid_for(brief))
    assert "couverture" not in score(plan, brief).as_dict()


def test_adjacency_judges_each_relation_by_what_it_asked_for():
    """CONNECTED needs a door; SEPARATED needs no wall at all."""
    brief, graph = apartment_brief(), apartment_graph()
    plan = seed_tree().realise(envelope_of(brief), brief, grid_for(brief))
    detail = score(plan, brief, graph).details["adjacences"]

    assert set(detail) == {f"{r.a}~{r.b}" for r in graph.relations}
    fabric = plan.to_fabric(P)
    for relation in graph.relations:
        run = fabric.shared_wall_length(*relation.pair)
        key = f"{relation.a}~{relation.b}"
        if relation.kind is R.CONNECTED:
            assert detail[key] == (run >= P.door_module)
        elif relation.kind is R.SEPARATED:
            assert detail[key] == (run == 0.0)


# --- how many bands the search may propose ----------------------------------


def test_a_programme_with_no_corridor_is_allowed_no_band_at_all():
    """2026-08-28. `band_budget` was `max(1, len(circulation_rooms))`, so a programme
    with no corridor was still allowed one band — and a band nobody can name is
    a candidate no envelope realises. Every such proposal buys a refusal.

    `band_names` is the same pool `realise` names bands from, so the budget and
    the naming can no longer disagree.
    """
    from planfgen.partition import UnrealisableTree
    from planfgen.search.moves import insert_band

    programme = Programme(
        [
            RoomSpec("Sejour", RoomType.SEJOUR, 30.0, "#888888"),
            RoomSpec("Chambre", RoomType.CHAMBRE, 16.0, "#888888"),
        ]
    )
    plain = SlicingTree(Cut(Direction.V, False, (Leaf("Sejour"), Leaf("Chambre"))))
    assert plain.band_names(programme) == []

    rng = random.Random(0)
    for _ in range(20):
        assert insert_band(plain, rng, budget=0) is plain

    # What the old `max(1, ...)` let through, one line down from the budget.
    banded = insert_band(plain, rng, budget=1)
    assert len(banded.bands()) == 1
    with pytest.raises(UnrealisableTree):
        banded.check_nameable(programme)


def test_the_budget_still_lets_a_corridor_become_a_spine():
    """The guard must not have closed the move it was written for."""
    brief = apartment_brief()
    flat = SlicingTree(
        Cut(Direction.V, False, (Leaf("Sejour"), Leaf("Cuisine")))
    )
    assert flat.band_names(brief.programme) == ["Couloir"]
    assert len(insert_band(flat, random.Random(1), budget=1).bands()) == 1
