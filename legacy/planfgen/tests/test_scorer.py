"""
tests/test_scorer.py
Unit tests for core/scorer.py.
"""

import json, os, pytest
from planfgen.core.geometry  import Rect
from planfgen.core.scorer    import score_layout, DEFAULT_WEIGHTS


FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "apartment_7rooms.json")

@pytest.fixture
def apartment():
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _make_placed(rooms_list):
    return {r["nom"]: r for r in rooms_list}


def test_scores_all_in_range(apartment):
    from planfgen.core.generator import generate_layout
    prog = apartment["programme"]
    adjs = [tuple(a) for a in apartment["adjacencies"]]
    W, H = 12.0, 9.0
    placed = generate_layout(prog, adjs, W, H, seed=0)
    frooms = [r["nom"] for r in prog if r.get("facade")]
    scores = score_layout(placed, adjs, W, H, frooms)
    for key in ["adjacences", "compacite", "facade", "couverture", "global"]:
        assert 0.0 <= scores[key] <= 1.0, f"{key} out of range: {scores[key]}"


def test_global_equals_weighted_sum(apartment):
    from planfgen.core.generator import generate_layout
    prog = apartment["programme"]
    adjs = [tuple(a) for a in apartment["adjacencies"]]
    W, H = 12.0, 9.0
    placed = generate_layout(prog, adjs, W, H, seed=5)
    frooms = [r["nom"] for r in prog if r.get("facade")]
    scores = score_layout(placed, adjs, W, H, frooms)
    expected = (
        0.40 * scores["adjacences"] +
        0.25 * scores["compacite"]  +
        0.20 * scores["facade"]     +
        0.15 * scores["couverture"]
    )
    assert scores["global"] == pytest.approx(expected, abs=1e-3)


def test_adj_details_length(apartment):
    from planfgen.core.generator import generate_layout
    prog = apartment["programme"]
    adjs = [tuple(a) for a in apartment["adjacencies"]]
    W, H = 12.0, 9.0
    placed = generate_layout(prog, adjs, W, H, seed=0)
    frooms = []
    scores = score_layout(placed, adjs, W, H, frooms)
    assert len(scores["adj_details"]) == len(adjs)


def test_adj_details_keys():
    placed = {
        "A": Rect(0, 0, 3, 3, "A"),
        "B": Rect(3, 0, 3, 3, "B"),
    }
    adjs = [("A", "B")]
    scores = score_layout(placed, adjs, 10, 10, facade_rooms=[])
    assert {"a", "b", "ok"} == set(scores["adj_details"][0].keys())


def test_perfect_adjacency_score():
    """Two rooms touching → adjacences = 1.0"""
    placed = {
        "A": Rect(0, 0, 4, 4, "A"),
        "B": Rect(4, 0, 4, 4, "B"),
    }
    adjs = [("A", "B")]
    scores = score_layout(placed, adjs, 10, 10, facade_rooms=[])
    assert scores["adjacences"] == pytest.approx(1.0)
    assert scores["adj_details"][0]["ok"] is True


def test_zero_adjacency_score():
    """Two rooms far apart → adjacences = 0.0"""
    placed = {
        "A": Rect(0, 0, 2, 2, "A"),
        "B": Rect(8, 8, 2, 2, "B"),
    }
    adjs = [("A", "B")]
    scores = score_layout(placed, adjs, 12, 12, facade_rooms=[])
    assert scores["adjacences"] == pytest.approx(0.0)


def test_custom_weights():
    placed = {"A": Rect(0, 0, 4, 4, "A"), "B": Rect(4, 0, 4, 4, "B")}
    adjs   = [("A", "B")]
    weights = {"adjacences": 1.0, "compacite": 0.0, "facade": 0.0, "couverture": 0.0}
    scores  = score_layout(placed, adjs, 10, 10, facade_rooms=[], weights=weights)
    assert scores["global"] == pytest.approx(scores["adjacences"], abs=1e-3)


def test_invalid_weights_raise():
    placed = {"A": Rect(0, 0, 3, 3, "A")}
    adjs   = []
    with pytest.raises(ValueError, match="sum"):
        score_layout(placed, adjs, 10, 10, facade_rooms=[],
                     weights={"adjacences": 0.5, "compacite": 0.5, "facade": 0.5, "couverture": 0.5})


def test_compacite_penalises_elongated_room():
    placed = {"Narrow": Rect(0, 0, 10, 1, "Narrow")}
    adjs   = []
    scores = score_layout(placed, adjs, 12, 12, facade_rooms=[])
    assert scores["compacite"] < 1.0


def test_facade_score_on_wall():
    placed = {"LivRoom": Rect(0, 0, 4, 4, "LivRoom")}
    adjs   = []
    scores = score_layout(placed, adjs, 12, 12, facade_rooms=["LivRoom"])
    assert scores["facade"] == pytest.approx(1.0)


def test_facade_score_in_center():
    placed = {"LivRoom": Rect(4, 3, 3, 3, "LivRoom")}
    adjs   = []
    scores = score_layout(placed, adjs, 12, 12, facade_rooms=["LivRoom"])
    assert scores["facade"] == pytest.approx(0.0)


def test_couverture_full_fill():
    """Room exactly fills envelope → couverture = 1.0"""
    placed = {"Big": Rect(0, 0, 10, 10, "Big")}
    adjs   = []
    scores = score_layout(placed, adjs, 10, 10, facade_rooms=[])
    assert scores["couverture"] == pytest.approx(1.0)
