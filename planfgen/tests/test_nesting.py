"""Nested plans — a WC off the entree, a bedroom off a degagement — exist, and why
the search does not reach them. PROGRESS.md S27; `tools/probe_construct.py`.

The two `xfail(strict=True)` tests are the acceptance tests for work routed
elsewhere: each asserts the behaviour the S27 spec asks for, fails today for the
reason in its marker, and will XPASS — so fail — the day that work lands, which
is when the marker comes off.
"""

from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

import pytest

from planfgen.brief.regulation import MA_CASABLANCA, MA_ECONOMIQUE
from planfgen.evaluate.constraints import all_gates
from planfgen.partition import BandCut, Cut, Direction, Leaf, SlicingTree
from planfgen.search import envelope_of, evaluate, grid_for
from planfgen.studio.pipeline import attempts, fit

V, H = Direction.V, Direction.H

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "probe_construct.py"


def _probe():
    spec = importlib.util.spec_from_file_location("probe_construct", _TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("probe_construct", module)
    spec.loader.exec_module(module)
    return module


PROBE = _probe()


def _cut(d, a, b):
    return Cut(d, False, (a, b))


#: An F3 with a separate WC: the corridor runs from the street; SDB and WC open
#: off the entree hall; a degagement off the corridor serves the cuisine and Ch2.
#: Found by exhausting the two-move neighbourhood of a hand-built plan: 3 of
#: 34 505 neighbours pass every gate, 0 of 341 one-move neighbours do.
NESTED_F3 = SlicingTree(
    BandCut(V, (
        _cut(H, _cut(V, _cut(H, Leaf("SDB"), Leaf("WC")), Leaf("Entree")), Leaf("Sejour")),
        _cut(H, Leaf("Ch1"), BandCut(H, (Leaf("Cuisine"), Leaf("Ch2")))),
    ))
)


def _brief(profile):
    rooms, width, depth = PROBE.CASES["F3wc+deg"]
    return PROBE.brief_for(rooms, width, depth, profile)


def test_a_separate_wc_f3_with_a_degagement_exists():
    """On its own footprint, every gate passes: the 2 m2 WC is not impossible."""
    brief = fit(_brief(MA_CASABLANCA), NESTED_F3).brief
    plan = NESTED_F3.realise(envelope_of(brief), brief, grid_for(brief))
    assert all_gates(plan, brief) == (True, None)
    bands = sorted(c.nom for c in plan.cells if c.is_band)
    assert bands == ["Couloir", "Degagement"]
    wc = next(c for c in plan.cells if c.nom == "WC")
    assert min(wc.net_dims(brief.profile)) >= 0.90


@pytest.mark.xfail(strict=True, reason=(
    "S27 spec for planfgen-engine: the envelope must follow the tree. The search "
    "realises every candidate on the SEED's footprint, so a tree with more "
    "corridor than the seed misses its areas by 4.5-9 % against a 5 % gate."))
def test_a_degagement_can_be_accepted_on_the_search_footprint():
    tree0, fitting = attempts(_brief(MA_CASABLANCA))[0]
    assert len(tree0.bands()) == 1
    assert evaluate(NESTED_F3, fitting.brief, grid_for(fitting.brief), None, 0) is not None


@pytest.mark.xfail(strict=True, reason=(
    "S27, routed: two corridors meeting are an opening, not a door. On the decret "
    "a band's end is 0.80 + 0.10 = 0.90 m, under the 1.00 m door module, so a "
    "degagement can never join its corridor and reachability refuses the plan."))
def test_a_t_junction_joins_two_corridors_on_the_decret():
    brief = fit(_brief(MA_ECONOMIQUE), NESTED_F3).brief
    plan = NESTED_F3.realise(envelope_of(brief), brief, grid_for(brief))
    assert all_gates(plan, brief) == (True, None)


def test_the_constructive_probe_builds_a_separate_wc_plan():
    """What the studio's walk found 2 of 18 times, construction finds directly —
    once each tree is given its own footprint, which is the S27 spec."""
    rooms, width, depth = PROBE.CASES["F3wc"]
    brief = PROBE.brief_for(rooms, width, depth, MA_CASABLANCA)
    _, fitting = attempts(brief)[0]
    finder = PROBE.Finder(fitting.brief, envelope_of(fitting.brief), 1)
    rng = random.Random(1)
    valid = 0
    for _ in range(8):
        tree = finder.find(rng, 1, 100_000)
        if tree is None:
            continue
        own = fit(brief, tree).brief
        plan = tree.realise(envelope_of(own), own, grid_for(own))
        assert {c.nom for c in plan.cells if not c.is_band} == set(finder.rooms)
        valid += all_gates(plan, own)[0]
    assert valid, "no constructed tree passed every gate on its own footprint"
