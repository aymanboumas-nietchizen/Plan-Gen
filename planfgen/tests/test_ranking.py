"""Ranking valid plans — the core of `tools/probe_ranking.py` (PROGRESS.md S30).

Every plan here has passed every gate; these tests are about which comes first
and what the gallery shows. Nothing in them scores a gate.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "probe_ranking.py"


def _probe():
    if "probe_ranking" in sys.modules:
        return sys.modules["probe_ranking"]
    spec = importlib.util.spec_from_file_location("probe_ranking", _TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["probe_ranking"] = module
    spec.loader.exec_module(module)
    return module


PR = _probe()


def plan(key, adj, orient, circ, comp, rooms=(), globale=None):
    """A plan with the metric's own weights unless `globale` is given."""
    g = globale if globale is not None else 0.45 * adj + 0.2 * orient + 0.2 * circ + 0.15 * comp
    return PR.Plan(key, adj, orient, circ, comp, g, tuple(rooms))


SQUARE = (("Sejour", "SEJOUR", 4.0, 5.0), ("Ch1", "CHAMBRE", 3.0, 4.0))
SLOT = (("Sejour", "SEJOUR", 4.0, 5.0), ("SDB", "SDB", 1.7, 4.1))
TWO_SLOTS = SLOT + (("Entree", "ENTREE", 1.5, 3.3),)


def test_slots_are_counted_on_net_ratio_and_the_threshold_is_strict():
    assert plan("a", 1, 1, 1, 1, SQUARE).fentes == 0
    assert plan("b", 1, 1, 1, 1, SLOT).fentes == 1
    assert plan("c", 1, 1, 1, 1, TWO_SLOTS).fentes == 2
    exactly_two = (("Ch", "CHAMBRE", 2.0, 4.0),)
    assert plan("d", 1, 1, 1, 1, exactly_two).fentes == 0
    assert plan("b", 1, 1, 1, 1, SLOT).pire == pytest.approx(4.1 / 1.7)
    assert plan("b", 1, 1, 1, 1, SLOT).slot_rooms == ["SDB 1.70x4.10"]


def test_dominance_is_strict_somewhere():
    assert PR.dominates((1, 1), (1, 0))
    assert not PR.dominates((1, 1), (1, 1))
    assert not PR.dominates((1, 0), (0, 1))


def test_front_drops_dominated_and_keeps_one_plan_per_vector():
    a = plan("a", 0.9, 1.0, 0.5, 0.7, SLOT)
    b = plan("b", 0.7, 1.0, 0.5, 0.8, SQUARE)          # fewer slots: a trade
    c = plan("c", 0.6, 1.0, 0.5, 0.8, SQUARE)          # b beats it everywhere
    b2 = plan("b2", 0.7, 1.0, 0.5, 0.8, SQUARE, globale=0.1)  # same vector as b
    got = PR.front([a, b, c, b2])
    assert [p.key for p in got] == ["a", "b"]


def test_lexi_puts_the_fewest_slots_first_whatever_the_sum():
    a = plan("a", 1.0, 1.0, 1.0, 0.6, SLOT)
    b = plan("b", 0.5, 0.5, 0.5, 0.9, SQUARE)
    assert PR.rank_globale([a, b])[0] is a
    assert PR.rank_lexi([a, b])[0] is b
    c = plan("c", 0.6, 0.5, 0.5, 0.9, SQUARE)          # within the tier, the sum
    assert PR.rank_lexi([a, b, c])[0] is c


def test_a_concave_plan_is_on_the_front_but_no_weight_reaches_it():
    """The theorem, on three points: C trades evenly between A and B and sits
    below the line joining them, so every weight vector prefers A or B."""
    a = plan("a", 1.0, 0.0, 0.0, 0.0)
    b = plan("b", 0.0, 1.0, 0.0, 0.0)
    c = plan("c", 0.4, 0.4, 0.0, 0.0)
    plans = [a, b, c]
    assert {p.key for p in PR.front(plans)} == {"a", "b", "c"}
    reach = PR.linear_reach(plans, PR.metric_terms, PR.simplex(4, 20))
    assert reach == {0, 1}
    c_convex = plan("c", 0.6, 0.6, 0.0, 0.0)
    reach = PR.linear_reach([a, b, c_convex], PR.metric_terms, PR.simplex(4, 20))
    assert 2 in reach


def test_simplex_covers_the_corners_and_sums_to_one():
    w = PR.simplex(4, 20)
    assert len(w) == 1771
    assert all(abs(sum(v) - 1) < 1e-9 for v in w)
    assert (1.0, 0.0, 0.0, 0.0) in w and (0.0, 0.0, 0.0, 1.0) in w


def _pool():
    return [
        plan("best-sum", 1.0, 1.0, 0.9, 0.6, TWO_SLOTS),
        plan("one-slot", 0.9, 1.0, 0.9, 0.7, SLOT),
        plan("no-slot", 0.7, 0.5, 0.8, 0.8, SQUARE),
        plan("no-slot-circ", 0.6, 0.5, 1.0, 0.8, SQUARE),
        plan("dominated", 0.5, 0.5, 0.7, 0.8, SQUARE),
    ]


def test_gallery_is_headed_by_the_lexi_pick_and_holds_only_front_plans():
    pool = _pool()
    g = PR.gallery(pool, k=4)
    assert g[0].plan.key == "no-slot"
    keys = [pk.plan.key for pk in g]
    assert "dominated" not in keys
    assert len(set(keys)) == len(keys) == 4
    assert g[0].versus == {}


def test_gallery_explains_each_plan_against_the_head():
    g = {pk.plan.key: pk for pk in PR.gallery(_pool(), k=4)}
    best = g["best-sum"]
    assert "adjacences" in best.why and "orientation" in best.why
    assert best.versus["fentes"] == -2                  # two more slots than the head
    assert best.versus["adjacences"] == pytest.approx(0.3)
    assert "circulation" in g["no-slot-circ"].why


def test_gallery_is_deterministic_and_order_free():
    pool = _pool()
    a = [pk.plan.key for pk in PR.gallery(pool, k=3)]
    b = [pk.plan.key for pk in PR.gallery(list(reversed(pool)), k=3)]
    assert a == b


def test_gallery_is_no_larger_than_the_front():
    one = [plan("x", 1, 1, 1, 1, SQUARE), plan("y", 0.5, 0.5, 0.5, 0.5, SQUARE)]
    assert [pk.plan.key for pk in PR.gallery(one, k=4)] == ["x"]
    assert PR.gallery([], k=4) == []


def test_collect_is_deterministic_and_returns_what_generate_returns():
    """A real, small run through the engine: the pool is reproducible, and the
    plan `collect` says the run returned is the one `pipeline.generate` returns
    for the same brief and seed — so the pool describes the studio's search."""
    from planfgen.brief.regulation import MA_PROFILE
    from planfgen.studio.pipeline import generate

    a = PR.collect("F3", "placeholder", 1, 20)
    b = PR.collect("F3", "placeholder", 1, 20)
    assert a["plans"], "the F3 preset builds on the placeholder profile"
    assert [p.key for p in a["plans"]] == [p.key for p in b["plans"]]
    brief, graph = PR.case_brief("F3", MA_PROFILE)
    run = generate(brief, graph, 1, 20)
    assert PR.plan_of(run.result, "anneal").key == a["returned"]
    assert a["returned"] in {p.key for p in a["plans"]}


def test_the_slot_free_constructor_reaches_plans_the_studio_never_returns():
    """DEMO's returned plan has a slot room in 11 of 18 runs (S30 sweep), yet a
    slot-free plan exists: the constrained construction builds it, and it
    passes every gate with every judged room within 2:1."""
    from planfgen.brief.regulation import MA_CASABLANCA
    from planfgen.search import envelope_of, evaluate, grid_for
    from planfgen.studio.pipeline import attempts

    brief, graph = PR.case_brief("DEMO", MA_CASABLANCA)
    found = None
    for _, fitting in attempts(brief):
        b = fitting.brief
        for tree in PR.construct_slot_free(b, envelope_of(b), 0, 6, 200_000):
            result = evaluate(tree, b, grid_for(b), graph, 0)
            if result is not None and PR.plan_of(result, "").fentes == 0:
                found = result
                break
        if found:
            break
    assert found is not None
    assert PR.plan_of(found, "construct").pire <= PR.SLOT


def _off_wall(p, ecart):
    from dataclasses import replace
    return replace(p, ecart=ecart)


def test_wall_to_wall_heads_the_list_and_the_slot_free_plan_is_shown_beside_it():
    """F4's shape: every wall-to-wall plan has the slot cuisine, the slot-free
    plans stop 1.2 m short of a party wall. The head keeps the pipeline's
    wall-to-wall order; the gallery's second plan is the slot-free one, and
    says what it costs."""
    walled = plan("walled", 0.8, 0.6, 0.8, 0.7, SLOT)
    short = _off_wall(plan("short", 0.7, 0.4, 0.8, 0.8, SQUARE), 1.2)
    assert PR.rank_lexi([walled, short])[0] is walled
    assert PR.rank_fentes([walled, short])[0] is short
    g = PR.gallery([walled, short], k=4)
    assert [pk.plan.key for pk in g] == ["walled", "short"]
    assert g[1].versus["fentes"] == 1
    assert g[1].versus["ecart"] == pytest.approx(-1.2)
    assert "fentes" in g[1].why and "ecart" in g[0].why


def test_a_one_plan_gallery_does_not_add_the_slot_free_plan():
    walled = plan("walled", 0.8, 0.6, 0.8, 0.7, SLOT)
    short = _off_wall(plan("short", 0.7, 0.4, 0.8, 0.8, SQUARE), 1.2)
    assert [pk.plan.key for pk in PR.gallery([walled, short], k=1)] == ["walled"]
