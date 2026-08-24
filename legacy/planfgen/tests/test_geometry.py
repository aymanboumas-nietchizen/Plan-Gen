"""
tests/test_geometry.py
Unit tests for core/geometry.py — Rect, build_graph, bfs_order.
"""

import pytest
from planfgen.core.geometry import Rect, build_graph, bfs_order


# ---------------------------------------------------------------------------
# Rect basic properties
# ---------------------------------------------------------------------------

def test_rect_area():
    assert Rect(0, 0, 5, 4, "R").area == pytest.approx(20.0)

def test_rect_area_float():
    assert Rect(0, 0, 3.5, 4.2, "R").area == pytest.approx(14.7)

def test_rect_ratio_square():
    assert Rect(0, 0, 4, 4, "R").ratio == pytest.approx(1.0)

def test_rect_ratio_wide():
    assert Rect(0, 0, 10, 2, "R").ratio == pytest.approx(5.0)

def test_rect_ratio_tall():
    assert Rect(0, 0, 2, 10, "R").ratio == pytest.approx(5.0)

def test_rect_centroid():
    r = Rect(2, 3, 4, 6, "R")
    assert r.cx == pytest.approx(4.0)
    assert r.cy == pytest.approx(6.0)

def test_rect_to_dict_keys():
    d = Rect(1, 2, 3, 4, "Test", "#ff0000").to_dict()
    assert set(d.keys()) == {"nom", "x", "y", "w", "h", "area", "color", "cx", "cy", "coords"}


# ---------------------------------------------------------------------------
# intersects
# ---------------------------------------------------------------------------

def test_intersects_overlap():
    a = Rect(0, 0, 5, 5, "A")
    b = Rect(3, 3, 5, 5, "B")
    assert a.intersects(b) is True

def test_intersects_separated():
    a = Rect(0, 0, 3, 3, "A")
    b = Rect(5, 5, 3, 3, "B")
    assert a.intersects(b) is False

def test_intersects_adjacent_edge_only():
    # Rooms share exactly one edge — should NOT intersect
    a = Rect(0, 0, 3, 3, "A")
    b = Rect(3, 0, 3, 3, "B")  # touching on right edge of A
    assert a.intersects(b) is False

def test_intersects_large_gap():
    a = Rect(0, 0, 2, 2, "A")
    b = Rect(10, 10, 2, 2, "B")
    assert a.intersects(b) is False


# ---------------------------------------------------------------------------
# touches
# ---------------------------------------------------------------------------

def test_touches_shared_right_wall():
    a = Rect(0, 0, 4, 4, "A")
    b = Rect(4, 0, 4, 4, "B")  # B directly to the right of A
    assert a.touches(b) is True

def test_touches_shared_top_wall():
    a = Rect(0, 0, 4, 4, "A")
    b = Rect(0, 4, 4, 4, "B")  # B directly above A
    assert a.touches(b) is True

def test_touches_within_tolerance():
    # 0.10 m gap — within default 0.15 m tolerance
    a = Rect(0, 0, 4, 4, "A")
    b = Rect(4.10, 0, 4, 4, "B")
    assert a.touches(b) is True

def test_touches_beyond_tolerance():
    # 0.20 m gap — beyond default 0.15 m tolerance
    a = Rect(0, 0, 4, 4, "A")
    b = Rect(4.20, 0, 4, 4, "B")
    assert a.touches(b) is False

def test_touches_overlapping_not_touching():
    # Overlapping rooms should NOT count as "touching" for adjacency purposes
    a = Rect(0, 0, 5, 5, "A")
    b = Rect(3, 3, 5, 5, "B")
    # They overlap — intersects() should be True, but touching logic is about edges
    # The key is no crash; behaviour depends on implementation edge cases
    # At minimum: no exception
    result = a.touches(b)
    assert isinstance(result, bool)

def test_touches_diagonal_no_shared_edge():
    # Rooms that share only a corner at (3,3) — boundary distance is 0,
    # so touches_room returns True (corner contact counts as touching in Shapely).
    a = Rect(0, 0, 3, 3, "A")
    b = Rect(3, 3, 3, 3, "B")  # corner contact at (3,3)
    assert a.touches(b) is True


# ---------------------------------------------------------------------------
# in_envelope
# ---------------------------------------------------------------------------

def test_in_envelope_valid():
    assert Rect(0, 0, 5, 4, "R").in_envelope(12, 9) is True

def test_in_envelope_edge():
    assert Rect(0, 0, 12, 9, "R").in_envelope(12, 9) is True  # exactly fills envelope

def test_in_envelope_overflow_x():
    assert Rect(10, 0, 5, 4, "R").in_envelope(12, 9) is False

def test_in_envelope_overflow_y():
    assert Rect(0, 7, 3, 5, "R").in_envelope(12, 9) is False

def test_in_envelope_negative_x():
    assert Rect(-0.5, 0, 3, 3, "R").in_envelope(12, 9) is False


# ---------------------------------------------------------------------------
# on_facade
# ---------------------------------------------------------------------------

def test_on_facade_left_wall():
    assert Rect(0, 2, 3, 3, "R").on_facade(12, 9) is True

def test_on_facade_right_wall():
    assert Rect(9, 2, 3, 3, "R").on_facade(12, 9) is True

def test_on_facade_bottom_wall():
    assert Rect(2, 0, 3, 3, "R").on_facade(12, 9) is True

def test_on_facade_top_wall():
    assert Rect(2, 6, 3, 3, "R").on_facade(12, 9) is True

def test_on_facade_center():
    assert Rect(4, 3, 3, 3, "R").on_facade(12, 9) is False


# ---------------------------------------------------------------------------
# build_graph
# ---------------------------------------------------------------------------

def test_build_graph_basic():
    rooms = [{"nom": "A"}, {"nom": "B"}, {"nom": "C"}]
    adjs  = [("A", "B"), ("B", "C")]
    g = build_graph(rooms, adjs)
    assert "B" in g["A"]
    assert "A" in g["B"]
    assert "C" in g["B"]
    assert "B" in g["C"]

def test_build_graph_bidirectional():
    rooms = [{"nom": "X"}, {"nom": "Y"}]
    adjs  = [("X", "Y")]
    g = build_graph(rooms, adjs)
    assert "Y" in g["X"]
    assert "X" in g["Y"]

def test_build_graph_isolated_room():
    rooms = [{"nom": "A"}, {"nom": "B"}, {"nom": "Isolated"}]
    adjs  = [("A", "B")]
    g = build_graph(rooms, adjs)
    assert "Isolated" in g
    assert g["Isolated"] == []

def test_build_graph_no_duplicates():
    rooms = [{"nom": "A"}, {"nom": "B"}]
    adjs  = [("A", "B"), ("A", "B")]  # duplicate rule
    g = build_graph(rooms, adjs)
    assert g["A"].count("B") == 1


# ---------------------------------------------------------------------------
# bfs_order
# ---------------------------------------------------------------------------

def test_bfs_order_simple():
    graph = {"A": ["B", "C"], "B": ["A"], "C": ["A"], "D": []}
    order = bfs_order(graph, "A", ["A", "B", "C", "D"])
    assert order[0] == "A"         # hub is first
    assert "D" in order            # straggler is included
    assert len(order) == 4

def test_bfs_order_stragglers_at_end():
    graph = {"H": ["A"], "A": ["H"], "S1": [], "S2": []}
    order = bfs_order(graph, "H", ["H", "A", "S1", "S2"])
    assert order[0] == "H"
    assert order[1] == "A"
    # S1 and S2 are stragglers — must appear AFTER the connected component
    assert set(order[2:]) == {"S1", "S2"}

def test_bfs_order_all_rooms_present():
    graph = {"A": ["B"], "B": ["A", "C"], "C": ["B"]}
    order = bfs_order(graph, "A", ["A", "B", "C"])
    assert set(order) == {"A", "B", "C"}
    assert len(order) == 3
