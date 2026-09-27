"""Studio tests — the stages have to look like different things.

The renderers are pure string building, so they can be tested without running
Streamlit. What is checked is the claim the stage selector makes: L1 is a graph
with no geometry in it, and L2 is geometry with no graph in it.
"""

from __future__ import annotations

import pytest

from planfgen.studio import partition_svg, topology_svg

from planfgen.tests.test_openings import FLAT_RELATIONS, topology_for
from planfgen.tests.test_search import (
    apartment_brief,
    apartment_graph,
    seed_tree,
)
from planfgen.search import envelope_of, grid_for
from planfgen.brief import MA_PROFILE as P
from planfgen.topology import ProgrammeGraph, Relation, RelationType


def test_the_organigramme_is_a_graph_and_nothing_else():
    """One node per room, one line per relation, and no metres anywhere."""
    topology = topology_for(FLAT_RELATIONS)
    svg = topology_svg(topology.graph, topology.programme)

    assert svg.count("<circle") == len(topology.graph.noms) == 7
    assert svg.count("<line") == len(FLAT_RELATIONS)
    assert "m2" not in svg, "L1 has no areas because L1 has no geometry"
    assert "No wall has been drawn" in svg


def test_relation_kinds_are_drawn_differently():
    from planfgen.studio.render import RELATION_STYLE
    from planfgen.topology import Relation, RelationType as R

    graph = ProgrammeGraph(
        [
            Relation("A", "B", R.CONNECTED),
            Relation("B", "C", R.SEPARATED),
        ]
    )
    svg = topology_svg(graph)
    for kind in (R.CONNECTED, R.SEPARATED):
        assert RELATION_STYLE[kind][0] in svg


def test_an_empty_graph_still_renders():
    assert topology_svg(ProgrammeGraph()).startswith("<svg")


def test_the_partition_view_shows_net_against_target():
    brief = apartment_brief()
    plan = seed_tree().realise(envelope_of(brief), brief, grid_for(brief))
    svg = partition_svg(plan, P)

    assert svg.count("<rect") == len(plan.cells) + 1, "one per cell, plus the page"
    for cell in plan.cells:
        assert f">{cell.nom}<" in svg
    assert ">band<" in svg, "the corridor has a width, not a target"
    assert "net / target" in svg


def test_the_two_views_are_not_the_same_picture():
    """The argument of the whole rewrite, as an assertion."""
    brief = apartment_brief()
    plan = seed_tree().realise(envelope_of(brief), brief, grid_for(brief))

    graph_view = topology_svg(apartment_graph(), brief.programme)
    plan_view = partition_svg(plan, P)

    assert "<circle" in graph_view and "<circle" not in plan_view
    assert "<rect" in plan_view
    assert graph_view != plan_view


# --- the app itself ---------------------------------------------------------

streamlit = pytest.importorskip("streamlit", reason="the studio is an optional extra")

from pathlib import Path  # noqa: E402

from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).parent.parent / "studio" / "app.py")


def run_app(timeout: float = 120.0) -> AppTest:
    """The app, run headlessly. No browser, no server, no clicking."""
    app = AppTest.from_file(APP, default_timeout=timeout)
    app.run()
    return app


def test_the_app_runs_and_shows_the_budget_before_generating():
    """A brief that cannot be built is not a generation problem, so the budget
    is on the page before the button is."""
    app = run_app()

    assert not app.exception, app.exception
    assert any("gross" in block.value and "habitable" in block.value
               for block in app.code), "the feasibility budget"
    assert app.button, "the Generer button"
    assert not app.tabs, "nothing is generated until it is asked for"


def test_generating_produces_the_four_stages_plan_first():
    """THE stage selector: one run, shown at L3, L8, L2 and L1. The plan is
    what an architect came for, so a result opens on it — it used to open on
    the organigramme, which the page itself calls what v1 shipped."""
    app = run_app()
    app.button[0].click().run()

    assert not app.exception, app.exception
    labels = [tab.label for tab in app.tabs]
    assert labels == ["L3 Plan", "L8 Dessin", "L2 Partition", "L1 Topologie"]


def test_the_result_survives_a_rerun():
    """Streamlit reruns the script on every interaction, and the button reads
    True for one run only. The plan used to vanish on the next one — a DXF
    download was enough to discard it."""
    app = run_app()
    app.button[0].click().run()
    app.run()

    assert not app.exception, app.exception
    assert app.tabs, "the plan is still on the page after a rerun"
    assert not any("a change" in w.value for w in app.warning), "nothing is stale"


def test_a_changed_brief_marks_the_result_stale():
    app = run_app()
    app.button[0].click().run()
    app.slider[0].set_value(90).run()   # north

    assert not app.exception, app.exception
    assert app.tabs, "the old plan is kept"
    assert any("a change" in w.value for w in app.warning), "and said to be old"


def test_the_run_reports_real_metrics():
    app = run_app()
    app.button[0].click().run()

    assert not app.exception, app.exception
    metrics = {m.label: m.value for m in app.metric}
    assert set(metrics) == {
        "Global",
        "Adjacences",
        "Orientation",
        "Circulation",
        "Erreur surface",
        "Emprise",
    }
    assert 0.0 < float(metrics["Global"]) <= 1.0
    assert float(metrics["Erreur surface"].rstrip(" %")) < 5.0


def test_an_infeasible_brief_stops_before_generating():
    """It says so and stops, rather than generating something impossible."""
    app = AppTest.from_file(APP, default_timeout=120.0)
    app.run()
    app.number_input[0].set_value(7.0).run()   # width
    app.number_input[1].set_value(7.0).run()   # depth

    assert not app.exception, app.exception
    assert app.error, "an infeasible brief is an error, not a warning"
    assert not app.tabs


# --- the tree the studio seeds ----------------------------------------------
#
# `AppTest` has no `data_editor` element and cannot delete a row, so the one
# input that used to break the page — the programme table with `Couloir`
# removed — is unreachable from a test that drives the page. That is why the
# decision lives in `studio/seed.py` as a function with a return value: these
# tests drive the studio's own answer, not a browser.

from shapely.geometry import Polygon  # noqa: E402

from planfgen.brief import (  # noqa: E402
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
from planfgen.evaluate import AREA_TOLERANCE  # noqa: E402
from planfgen.partition import (  # noqa: E402
    BandCut,
    Direction,
    SlicingTree,
    UnrealisableTree,
)
from planfgen.search import RunStats, anneal  # noqa: E402
from planfgen.studio.seed import seed_tree as studio_seed_tree, spine_note  # noqa: E402

#: The studio's own default programme. `Couloir` is last so that `[:5]` is the
#: exact edit a user makes when they delete the corridor row.
STUDIO_ROOMS = [
    ("Sejour", "SEJOUR", 33.8, "S"),
    ("Cuisine", "CUISINE", 13.5, "N"),
    ("Ch1", "CHAMBRE_PRINCIPALE", 19.2, "N"),
    ("Ch2", "CHAMBRE", 15.8, "S"),
    ("SDB", "SDB", 10.2, "E"),
    ("Couloir", "COULOIR", 8.0, ""),
]


def studio_brief(rooms, width: float = 12.0, height: float = 10.0):
    """A brief built the way `app.py` builds one: the sidebar's own defaults."""
    programme = Programme(
        [
            RoomSpec(
                nom=nom,
                kind=RoomType[kind],
                surface_utile=area,
                couleur="#888888",
                orientation_pref=Orientation[pref] if pref else None,
            )
            for nom, kind, area, pref in rooms
        ]
    )
    parcel = Parcel(
        outline=Polygon([(0, 0), (width, 0), (width, height), (0, height)]),
        edges=[
            EdgeSpec(0, EdgeType.STREET),
            EdgeSpec(1, EdgeType.MITOYEN),
            EdgeSpec(2, EdgeType.COURT),
            EdgeSpec(3, EdgeType.MITOYEN),
        ],
        north=0.0,
        entry_edge=0,
    )
    budget = check_feasibility(programme, parcel, P)
    return Brief(programme, parcel, P, budget), budget


def test_a_programme_with_a_corridor_still_gets_a_band():
    """The normal case, unchanged: the spine is named by `Couloir`."""
    brief, budget = studio_brief(STUDIO_ROOMS)
    tree = studio_seed_tree(brief.programme)

    assert len(tree.bands()) == 1
    assert tree.band_names(brief.programme) == ["Couloir"]
    tree.check_nameable(brief.programme)
    assert spine_note(brief.programme, budget).banded


def test_a_corridorless_programme_is_seeded_without_a_band():
    """Deleting the `Couloir` row is a plan with no corridor, not a broken tree.

    A `BandCut` IS a corridor and has to be named by a circulation room, so the
    unconditional band the studio used to build was a tree no envelope could
    realise. The regression anchor is the first assertion: that tree still
    raises, which is why `seed_tree` must not build it.
    """
    brief, _ = studio_brief(STUDIO_ROOMS[:5])
    noms = [r.nom for r in brief.programme.rooms]
    assert "Couloir" not in noms

    from planfgen.studio.seed import _chain

    unnameable = SlicingTree(
        BandCut(Direction.V, (_chain(noms[:2]), _chain(noms[2:])))
    )
    with pytest.raises(UnrealisableTree):
        unnameable.check_nameable(brief.programme)

    tree = studio_seed_tree(brief.programme)
    assert tree.bands() == [], "no circulation room, so no band to name"
    assert sorted(leaf.nom for leaf in tree.leaves()) == sorted(noms)
    tree.check_nameable(brief.programme)


def test_the_corridorless_plan_is_one_the_engine_actually_builds():
    """Measured 2026-08-28: not a plan in principle, a plan in the run log."""
    rooms = [(nom, kind, area * 1.125, pref) for nom, kind, area, pref in STUDIO_ROOMS[:5]]
    brief, budget = studio_brief(rooms)
    note = spine_note(brief.programme, budget)
    assert note.kind == "open", note.message

    stats = RunStats()
    best = anneal(brief, studio_seed_tree(brief.programme), 120, seed=0, stats=stats)

    assert best, stats.explain()
    plan = best[0].plan
    assert plan.circulation_cells == [], "no corridor asked for, none delivered"
    assert plan.max_area_error(P) <= AREA_TOLERANCE


def test_the_uncalibrated_corridorless_programme_now_generates():
    """The default programme with its corridor deleted used to be refused by
    the area gate: 12.6 % of slack spread over the rooms, and nothing to absorb
    it. The studio now sizes the footprint first, so the slack stays unbuilt."""
    brief, budget = studio_brief(STUDIO_ROOMS[:5])
    assert spine_note(brief.programme, budget).kind == "open"

    run = generate(brief, ProgrammeGraph([]), seed=1, iterations=200)

    assert run.ok, run.stats.explain()
    assert run.result.plan.max_area_error(P) <= AREA_TOLERANCE


def test_too_few_rooms_is_refused_on_the_page_not_as_a_traceback():
    """`seed_tree`'s ValueError was raised OUTSIDE the app's try/except, so a
    one-room programme surfaced as a raw Streamlit traceback. It is refused in
    the feasibility section now, where an unbuildable brief is already refused."""
    brief, budget = studio_brief(STUDIO_ROOMS[:1])
    note = spine_note(brief.programme, budget)

    assert budget.ok, "one room fits the parcel; the refusal is not about area"
    assert not note.ok and "au moins 2 pieces" in note.message
    with pytest.raises(ValueError):
        studio_seed_tree(brief.programme)


def test_the_page_says_what_the_spine_will_be_before_the_button():
    """The note is rendered above `Generer`, like the budget it follows."""
    app = run_app()

    assert not app.exception, app.exception
    assert any("bande de circulation" in caption.value for caption in app.caption)
    assert not app.error


# --- the pipeline, and what the studio offers to start from ------------------

from planfgen.brief.regulation import PROFILES  # noqa: E402
from planfgen.studio.pipeline import fit, generate  # noqa: E402
from planfgen.studio.presets import PRESETS  # noqa: E402


def preset_brief(key: str, profile):
    preset = PRESETS[key]
    brief, budget = studio_brief(
        [(n, k, a, o) for n, k, a, o in preset.rooms], preset.width, preset.depth
    )
    brief = Brief(brief.programme, brief.parcel, profile,
                  check_feasibility(brief.programme, brief.parcel, profile))
    graph = ProgrammeGraph(
        [Relation(a, b, RelationType[k], w) for a, b, k, w in preset.relations]
    )
    return brief, graph


@pytest.mark.parametrize("profile_name", sorted(PROFILES))
@pytest.mark.parametrize("key", sorted(PRESETS))
def test_every_preset_generates_on_every_profile(key, profile_name):
    """A preset that generates nothing is worse than no preset. Four seeds,
    because one is a coin toss (F4 on the decret: 3 of 4, 2026-09-27)."""
    brief, graph = preset_brief(key, PROFILES[profile_name])
    assert brief.budget.ok, brief.budget.explain()

    runs = [generate(brief, graph, seed=s, iterations=200) for s in range(1, 5)]

    assert any(run.ok for run in runs), runs[-1].stats.explain()


def test_the_studio_used_to_refuse_a_real_programme():
    """The regression anchor. The F3 preset on its lot, built on the whole
    parcel as the studio did until 2026-09-27: the band cannot absorb the slack,
    every room overshoots together, and the area gate refuses every candidate."""
    brief, graph = preset_brief("F3", P)
    stats = RunStats()
    tree = studio_seed_tree(brief.programme)

    assert anneal(brief, tree, 200, seed=1, graph=graph, stats=stats) == []
    assert stats.rejected_by == {"area": 200}, stats.explain()
    assert generate(brief, graph, seed=1, iterations=200).ok


def test_a_lot_too_small_scales_the_rooms_and_says_so():
    """`fit_brief`'s other outcome: the whole lot, and every room smaller."""
    brief, _ = preset_brief("F3", P)
    small = Brief(
        brief.programme,
        Parcel(
            outline=Polygon([(0, 0), (7, 0), (7, 8), (0, 8)]),
            edges=brief.parcel.edges,
            north=0.0,
            entry_edge=0,
        ),
        P,
        brief.budget,
    )
    fitting = fit(small, studio_seed_tree(small.programme))

    assert fitting.shrunk
    assert "reduite" in fitting.note


def test_a_fitted_footprint_leaves_the_rest_of_the_lot_unbuilt():
    brief, _ = preset_brief("F4", P)
    fitting = fit(brief, studio_seed_tree(brief.programme))

    assert not fitting.shrunk
    assert fitting.footprint.w * fitting.footprint.h < brief.parcel.outline.area
    assert "n'est pas bati" in fitting.note
