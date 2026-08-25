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
from planfgen.topology import ProgrammeGraph


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


def test_generating_produces_the_four_stages():
    """THE stage selector: one run, shown at L1, L2, L3 and L8."""
    app = run_app()
    app.button[0].click().run()

    assert not app.exception, app.exception
    labels = [tab.label for tab in app.tabs]
    assert labels == ["L1 Topologie", "L2 Partition", "L3 Fabrique", "L8 Dessin"]


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
