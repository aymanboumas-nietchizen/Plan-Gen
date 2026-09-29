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
from planfgen.fabric.plan import junction_module
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


def test_a_degagement_can_be_accepted_on_the_search_footprint():
    """The envelope follows the tree (S28): a tree with more corridor than the
    seed is realised on a footprint solved for itself, not on the seed's —
    where it missed its areas by 4.5-9 % against a 5 % gate."""
    tree0, fitting = attempts(_brief(MA_CASABLANCA))[0]
    assert len(tree0.bands()) == 1
    assert evaluate(NESTED_F3, fitting.brief, grid_for(fitting.brief), None, 0) is not None


def test_a_t_junction_joins_two_corridors_on_the_decret():
    """Two corridors meeting are an opening, not a door. On the decret a band's
    end is 0.80 + 0.10 = 0.90 m, under the 1.00 m door module; it joins over
    `junction_module` (S28, approved by the user)."""
    brief = fit(_brief(MA_ECONOMIQUE), NESTED_F3).brief
    plan = NESTED_F3.realise(envelope_of(brief), brief, grid_for(brief))
    assert all_gates(plan, brief) == (True, None)


def _decret_fabric():
    brief = fit(_brief(MA_ECONOMIQUE), NESTED_F3).brief
    plan = NESTED_F3.realise(envelope_of(brief), brief, grid_for(brief))
    return plan.to_fabric(brief.profile), brief


def test_the_junction_rule_is_for_circulation_only():
    """A room still needs the whole door module: 0.90 m of wall joins the
    degagement to its corridor and would join nothing else."""
    fabric, brief = _decret_fabric()
    profile = brief.profile
    assert junction_module(profile) == pytest.approx(0.80)
    run = fabric.shared_wall_length("Couloir", "Degagement")
    assert profile.corridor_clear <= run < profile.door_module
    assert fabric.door_capable("Couloir", "Degagement")
    assert "Degagement" in fabric.adjacency_graph()["Couloir"]
    for a in fabric.spaces:
        for b in fabric.spaces:
            if a != b and not fabric.is_passage(a, b) and fabric.door_capable(a, b):
                assert fabric.shared_wall_length(a, b) >= profile.door_module - 1e-9


def test_l6_opens_the_junction_with_no_leaf_and_draws_a_gap(tmp_path):
    """The junction is a `Passage`: no door, no swing, a gap in the DXF wall."""
    import ezdxf

    from planfgen.document.dxf import export_dxf
    from planfgen.openings import Passage, place_openings

    fabric, brief = _decret_fabric()
    graph = PROBE.graph_for(PROBE.CASES["F3wc+deg"][0])

    class _Topology:
        pass

    topology = _Topology()
    topology.graph = graph
    report = place_openings(fabric, topology, brief.profile, brief.programme)
    junction = [p for p in report.passages if set(p.between) == {"Couloir", "Degagement"}]
    assert len(junction) == 1
    passage = junction[0]
    assert isinstance(passage, Passage)
    assert passage.width == pytest.approx(brief.profile.corridor_clear)
    low, high = passage.span
    assert 0.0 <= low < high <= passage.wall.length + 1e-9
    # no door leaf anywhere on that wall
    assert not any(door.wall is passage.wall for door in report.doors)

    path = tmp_path / "junction.dxf"
    export_dxf(fabric, path, report)
    doc = ezdxf.readfile(path)
    wall = passage.wall
    axis = 0 if wall.is_horizontal else 1
    origin = min(wall.p0[axis], wall.p1[axis])
    gap_lo, gap_hi = origin + low, origin + high
    across = wall.p0[1 - axis]
    solids = [e for e in doc.modelspace().query("LWPOLYLINE")]
    for e in solids:
        pts = [(p[0], p[1]) for p in e.get_points()]
        along = [p[axis] for p in pts]
        cross = [p[1 - axis] for p in pts]
        if min(cross) - 1e-6 <= across <= max(cross) + 1e-6:
            # no wall solid crossing this axis may cover the gap's middle
            mid = (gap_lo + gap_hi) / 2
            assert not (min(along) + 1e-6 < mid < max(along) - 1e-6), pts


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


def test_an_envelope_given_from_above_is_kept():
    """`follow=False`: a unit on a floor plate is realised on the envelope it
    is given — here the seed's, on which the degagement tree misses its areas."""
    tree0, fitting = attempts(_brief(MA_CASABLANCA))[0]
    assert evaluate(NESTED_F3, fitting.brief, grid_for(fitting.brief), None, 0,
                    follow=False) is None


def test_refit_keeps_the_footprint_where_the_tree_asks_for_its_size():
    """Re-solving the seed's own tree lands on the seed's size, so the footprint
    — and wherever a slide has put it — is kept as it stands."""
    from dataclasses import replace

    from planfgen.search import refit

    tree0, fitting = attempts(_brief(MA_CASABLANCA))[0]
    brief = fitting.brief
    assert refit(tree0, brief) is brief
    moved = replace(brief, footprint=replace(brief.footprint, y=brief.footprint.y + 0.3))
    assert refit(tree0, moved) is moved
    cache: dict = {}
    other = refit(NESTED_F3, brief, cache)
    assert other.footprint != brief.footprint
    assert refit(NESTED_F3, brief, cache) == other and len(cache) == 1
