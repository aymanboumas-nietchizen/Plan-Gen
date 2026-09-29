"""`search/construct.py` — building trees whose rooms furnish and are served.

The prototype is `tools/probe_construct.py` (S27); these pin the engine port:
the closed-form furniture window agrees with the gate it stands for, what it
builds is a whole programme with the bands asked for, the same seed builds the
same trees, and a brief nothing can build is given up on quickly.
"""

from __future__ import annotations

import importlib.util
import random
import sys
import time
from pathlib import Path

import pytest

from planfgen.brief.programme import RoomType
from planfgen.brief.regulation import MA_CASABLANCA, MA_ECONOMIQUE
from planfgen.evaluate.constraints import all_gates
from planfgen.habitability.check import fits
from planfgen.habitability.furniture import FURNITURE
from planfgen.partition.plan import SpaceCell
from planfgen.search import envelope_of, evaluate, grid_for
from planfgen.search.construct import Constructor, construct, depth_windows
from planfgen.studio.pipeline import attempts, fit

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "probe_construct.py"


def _probe():
    spec = importlib.util.spec_from_file_location("probe_construct", _TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("probe_construct", module)
    spec.loader.exec_module(module)
    return module


PROBE = _probe()


def _case(name, profile):
    rooms, width, depth = PROBE.CASES[name]
    return PROBE.brief_for(rooms, width, depth, profile)


@pytest.mark.parametrize("kind", sorted(FURNITURE, key=lambda k: k.name))
def test_the_depth_window_is_the_furniture_gate_in_closed_form(kind):
    """For every depth p, p in the window iff a p x (a/p) room fits its spec."""
    spec = FURNITURE[kind]
    for area in (2.0, 5.0, 9.0, 13.0, 24.0):
        windows = depth_windows(area, kind)
        for step in range(1, 400):
            p = step * 0.025
            inside = any(a - 1e-9 <= p <= b + 1e-9 for a, b in windows)
            q = area / p
            short, long = min(p, q), max(p, q)
            gate = (short >= spec.min_side and long >= spec.min_long
                    and long / short <= spec.max_ratio)
            if abs(short - spec.min_side) < 1e-6 or abs(long - spec.min_long) < 1e-6:
                continue                       # on the boundary either answer is fair
            assert inside == gate, (kind, area, p, windows)


def test_the_leaf_test_is_the_furniture_gate():
    """No SpaceCell is built, but the answer is the one `fits` gives."""
    brief = _case("F3wc", MA_CASABLANCA)
    finder = Constructor(brief, envelope_of(brief))
    rng = random.Random(3)
    t = (0.30, 0.10, 0.10, 0.30)
    kinds = {0.30: "facade", 0.10: "cloison"}
    from planfgen.fabric.axis import WallKind
    for _ in range(2000):
        i = rng.randrange(finder.n)
        w, h = rng.uniform(0.5, 6), rng.uniform(0.5, 6)
        kind = brief.programme.by_nom(finder.noms[i]).kind
        spec = FURNITURE.get(kind)
        cell = SpaceCell(finder.noms[i], 0, 0, w, h, dict(zip(
            ("left", "right", "bottom", "top"), (WallKind(kinds[x]) for x in t))))
        a, b = cell.net_dims(brief.profile)
        expect = (spec is None or fits(cell, spec, brief.profile)) and a * b >= (
            brief.profile.min_area.get(kind) or 0.0)
        flags = (1, 1, 1 | 2, 1)               # served everywhere, street below
        got = finder._leaf_ok(i, w, h, t, flags, -1)
        if expect and kind is not RoomType.ENTREE:
            assert got, (finder.noms[i], w, h)
        if not expect:
            assert not got, (finder.noms[i], w, h)


def test_it_builds_whole_programmes_with_the_bands_asked_for():
    brief = _case("F3wc+deg", MA_CASABLANCA)
    _, fitting = attempts(brief)[0]
    trees = construct(fitting.brief, envelope_of(fitting.brief), seed=1)
    assert trees
    rooms = {r.nom for r in brief.programme.rooms if not r.kind.names_band}
    for tree in trees:
        assert {leaf.nom for leaf in tree.leaves()} == rooms
        assert 1 <= len(tree.bands()) <= 2
    assert any(len(tree.bands()) == 2 for tree in trees)


def test_constructed_trees_pass_every_gate_on_their_own_footprint():
    """A separate 2 m2 WC: what the walk found 2 of 18 times."""
    brief = _case("F3wc", MA_CASABLANCA)
    _, fitting = attempts(brief)[0]
    valid = 0
    for tree in construct(fitting.brief, envelope_of(fitting.brief), seed=1):
        own = fit(brief, tree).brief
        plan = tree.realise(envelope_of(own), own, grid_for(own))
        valid += all_gates(plan, own)[0]
        # and `evaluate` refits it on the search's own footprint
        valid += evaluate(tree, fitting.brief, grid_for(fitting.brief), None, 0) is not None
    assert valid >= 2


def test_the_same_seed_builds_the_same_trees():
    brief = _case("F4wc+deg", MA_ECONOMIQUE)
    _, fitting = attempts(brief)[0]
    rect = envelope_of(fitting.brief)
    assert construct(fitting.brief, rect, seed=7) == construct(fitting.brief, rect, seed=7)


def test_an_unbuildable_brief_is_given_up_quickly():
    """F2 on the decret furnishes on no one-band tree (S27 `--f2`): the search
    proves it or runs out of calls, in well under a second per attempt."""
    brief = _case("F2", MA_ECONOMIQUE)
    t0 = time.perf_counter()
    for _, fitting in attempts(brief):
        construct(fitting.brief, envelope_of(fitting.brief), seed=1)
    assert time.perf_counter() - t0 < 5.0


def test_a_hopeless_envelope_is_proven_empty_at_once():
    brief = _case("F3wc", MA_CASABLANCA)
    x, y, w, h = envelope_of(attempts(brief)[0][1].brief)
    finder = Constructor(attempts(brief)[0][1].brief, (x, y, w / 3, h / 3))
    assert finder.find(random.Random(1), 1) is None
    assert finder.proven_empty(1)
    assert finder.calls < 50


def test_best_start_prefers_a_constructed_tree_that_passes():
    from planfgen.search.construct import best_start

    brief = _case("F3wc", MA_CASABLANCA)
    tree0, fitting = attempts(brief)[0]
    grid = grid_for(fitting.brief)
    assert evaluate(tree0, fitting.brief, grid, None, 0) is None   # the seed fails
    start = best_start(fitting.brief, tree0, None, seed=1)
    assert start != tree0
    assert evaluate(start, fitting.brief, grid, None, 0) is not None


def test_best_start_falls_back_to_the_seed_when_nothing_passes():
    from planfgen.search.construct import best_start

    brief = _case("F2", MA_ECONOMIQUE)
    tree0, fitting = attempts(brief)[0]
    assert best_start(fitting.brief, tree0, None, seed=1) == tree0


@pytest.mark.parametrize("profile", [MA_ECONOMIQUE, MA_CASABLANCA])
def test_the_studio_builds_an_f3_with_a_separate_wc(profile):
    """Through `pipeline.generate`, as the studio runs it: 2 of 18 before S28."""
    from planfgen.studio.pipeline import generate

    rooms, width, depth = PROBE.CASES["F3wc"]
    brief = PROBE.brief_for(rooms, width, depth, profile)
    run = generate(brief, PROBE.graph_for(rooms), 1, 100)
    assert run.ok
    assert "WC" in {c.nom for c in run.result.plan.cells}
    assert run.openings is not None
