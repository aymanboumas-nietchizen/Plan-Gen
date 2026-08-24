"""L3a tests — noding the wall graph and reading faces back off it.

The reference case is a 2 x 2 grid inside a 6.00 x 4.00 m rectangle, cut at
x = 3.00 and y = 2.00, hand-built as six authored axes.
"""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from planfgen.fabric.axis import WallAxis, WallKind, segment_overlap
from planfgen.fabric.graph import WallGraph

EXACT = 1e-9


def grid_graph() -> WallGraph:
    """6.00 x 4.00 rectangle with a full-length cut at x=3.00 and one at y=2.00."""
    graph = WallGraph()
    for p0, p1, kind in [
        ((0, 0), (6, 0), WallKind.FACADE),
        ((0, 4), (6, 4), WallKind.FACADE),
        ((0, 0), (0, 4), WallKind.FACADE),
        ((6, 0), (6, 4), WallKind.FACADE),
        ((3, 0), (3, 4), WallKind.CLOISON),
        ((0, 2), (6, 2), WallKind.CLOISON),
    ]:
        graph.add(WallAxis(p0, p1, kind))
    return graph


def notched_graph() -> WallGraph:
    """The same rectangle with a 2 x 2 notch removed at the top right.

    Cuts at x=2.00 (full height), x=4.00 (up to the notch) and y=2.00 (across
    to the notch corner) leave five 2.00 x 2.00 faces.
    """
    graph = WallGraph()
    for p0, p1, kind in [
        ((0, 0), (6, 0), WallKind.FACADE),
        ((6, 0), (6, 2), WallKind.FACADE),
        ((6, 2), (4, 2), WallKind.FACADE),
        ((4, 2), (4, 4), WallKind.FACADE),
        ((4, 4), (0, 4), WallKind.FACADE),
        ((0, 4), (0, 0), WallKind.FACADE),
        ((2, 0), (2, 4), WallKind.CLOISON),
        ((4, 0), (4, 2), WallKind.CLOISON),
        ((0, 2), (4, 2), WallKind.CLOISON),
    ]:
        graph.add(WallAxis(p0, p1, kind))
    return graph


def face_at(faces: list[Polygon], x: float, y: float) -> Polygon:
    """The face whose centroid is at (x, y)."""
    for face in faces:
        cx, cy = face.centroid.coords[0]
        if abs(cx - x) < 1e-6 and abs(cy - y) < 1e-6:
            return face
    raise AssertionError(f"no face centred on ({x}, {y})")


# --- the axis primitive -----------------------------------------------------


def test_diagonal_axis_is_rejected():
    with pytest.raises(ValueError, match="axis-aligned only"):
        WallAxis((0, 0), (3, 3), WallKind.CLOISON)


def test_zero_length_axis_is_rejected():
    with pytest.raises(ValueError, match="zero-length"):
        WallAxis((1, 1), (1, 1), WallKind.CLOISON)


def test_endpoints_are_normalised_and_measured():
    wall = WallAxis((6, 0), (0, 0), WallKind.FACADE)
    assert wall.p0 == (0.0, 0.0) and wall.p1 == (6.0, 0.0)
    assert wall.length == pytest.approx(6.0)
    assert wall.is_horizontal and not wall.is_vertical
    assert wall.bounds == (0.0, 0.0, 6.0, 0.0)


def test_only_facade_and_porteur_are_bearing():
    assert WallKind.FACADE.bearing and WallKind.PORTEUR.bearing
    assert not WallKind.CLOISON.bearing and not WallKind.WET.bearing


def test_collinear_overlap():
    a = WallAxis((0, 0), (6, 0), WallKind.FACADE)
    assert a.collinear_overlap(WallAxis((3, 0), (9, 0), WallKind.CLOISON)) == 3.0
    # parallel but offset, perpendicular, and merely touching all share no run
    assert a.collinear_overlap(WallAxis((0, 2), (6, 2), WallKind.CLOISON)) == 0.0
    assert a.collinear_overlap(WallAxis((3, 0), (3, 4), WallKind.CLOISON)) == 0.0
    assert a.collinear_overlap(WallAxis((6, 0), (9, 0), WallKind.CLOISON)) == 0.0


def test_segment_overlap_is_symmetric():
    p, q = ((0, 0), (6, 0)), ((3, 0), (9, 0))
    assert segment_overlap(*p, *q) == segment_overlap(*q, *p) == 3.0


# --- the 2 x 2 grid ---------------------------------------------------------


def test_split_at_crossings_segment_count():
    """Each of the four sides splits once and each cut splits once: 6 -> 12."""
    graph = grid_graph()
    graph.split_at_crossings()
    assert len(graph.walls) == 12
    assert all(w.length == pytest.approx(2.0) or w.length == pytest.approx(3.0)
               for w in graph.walls)


def test_split_is_idempotent():
    graph = grid_graph()
    graph.split_at_crossings()
    once = sorted((w.p0, w.p1) for w in graph.walls)
    graph.split_at_crossings()
    assert sorted((w.p0, w.p1) for w in graph.walls) == once


def test_split_segments_inherit_their_parent_kind():
    graph = grid_graph()
    graph.split_at_crossings()
    perimeter = [w for w in graph.walls if w.kind is WallKind.FACADE]
    cuts = [w for w in graph.walls if w.kind is WallKind.CLOISON]
    assert len(perimeter) == 8 and len(cuts) == 4


def test_faces_are_four_equal_quarters():
    graph = grid_graph()
    graph.split_at_crossings()
    faces = graph.faces()
    assert len(faces) == 4
    for face in faces:
        assert face.area == pytest.approx(6.0, abs=EXACT)


def test_bounding_walls_are_four_per_face():
    graph = grid_graph()
    graph.split_at_crossings()
    for face in graph.faces():
        assert len(graph.bounding_walls(face)) == 4


def test_shared_length_of_horizontally_adjacent_faces():
    graph = grid_graph()
    graph.split_at_crossings()
    faces = graph.faces()
    left, right = face_at(faces, 1.5, 1.0), face_at(faces, 4.5, 1.0)
    assert graph.shared_length(left, right) == pytest.approx(2.0, abs=EXACT)


def test_shared_length_of_diagonally_opposite_faces_is_zero():
    """They meet at the point (3, 2). A corner is not a run of wall."""
    graph = grid_graph()
    graph.split_at_crossings()
    faces = graph.faces()
    lower_left, upper_right = face_at(faces, 1.5, 1.0), face_at(faces, 4.5, 3.0)
    assert graph.shared_length(lower_left, upper_right) == 0.0


def test_wall_between_adjacent_and_diagonal_faces():
    graph = grid_graph()
    graph.split_at_crossings()
    faces = graph.faces()
    lower_left = face_at(faces, 1.5, 1.0)
    wall = graph.wall_between(lower_left, face_at(faces, 4.5, 1.0))
    assert wall is not None
    assert (wall.p0, wall.p1) == ((3.0, 0.0), (3.0, 2.0))
    assert graph.wall_between(lower_left, face_at(faces, 4.5, 3.0)) is None


# --- the L-shaped case ------------------------------------------------------


def test_notched_outline_yields_five_faces():
    graph = notched_graph()
    graph.split_at_crossings()
    faces = graph.faces()
    assert len(faces) == 5
    for face in faces:
        assert face.area == pytest.approx(4.0, abs=EXACT)


def test_the_notch_is_not_a_face():
    """20 m2 of faces, not 24 — the removed corner encloses nothing."""
    graph = notched_graph()
    graph.split_at_crossings()
    faces = graph.faces()
    assert sum(f.area for f in faces) == pytest.approx(20.0, abs=EXACT)
    with pytest.raises(AssertionError):
        face_at(faces, 5.0, 3.0)
