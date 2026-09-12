"""
tests/test_generator.py
Unit tests for core/generator.py.
"""

import json
import os
import pytest
from planfgen.core.generator import generate_layout
from planfgen.core.geometry import Rect


FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "apartment_7rooms.json")

@pytest.fixture
def apartment():
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data

def _prog(data):
    return data["programme"]

def _adjs(data):
    return [tuple(a) for a in data["adjacencies"]]

def _env(data):
    return data["envelope"]["W"], data["envelope"]["H"]


def test_all_rooms_placed(apartment):
    prog = _prog(apartment)
    adjs = _adjs(apartment)
    W, H = _env(apartment)
    placed = generate_layout(prog, adjs, W, H, seed=0)
    assert len(placed) == len(prog)
    for r in prog:
        assert r["nom"] in placed, f"Room {r['nom']} missing from placed dict"


def test_no_room_overflows_envelope(apartment):
    prog = _prog(apartment)
    adjs = _adjs(apartment)
    W, H = _env(apartment)
    placed = generate_layout(prog, adjs, W, H, seed=0)
    for nom, rect in placed.items():
        assert rect.in_envelope(W, H), f"{nom} overflows envelope: x={rect.x}, y={rect.y}, w={rect.w}, h={rect.h}"


def test_no_overlaps_between_rooms(apartment):
    prog = _prog(apartment)
    adjs = _adjs(apartment)
    W, H = _env(apartment)
    placed = generate_layout(prog, adjs, W, H, seed=0)
    rects = list(placed.values())
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not rects[i].intersects(rects[j]), (
                f"Rooms {rects[i].nom} and {rects[j].nom} overlap"
            )


def test_seed_reproducibility(apartment):
    prog = _prog(apartment)
    adjs = _adjs(apartment)
    W, H = _env(apartment)
    placed_a = generate_layout(prog, adjs, W, H, seed=42)
    placed_b = generate_layout(prog, adjs, W, H, seed=42)
    for nom in placed_a:
        ra = placed_a[nom]
        rb = placed_b[nom]
        assert ra.x == rb.x and ra.y == rb.y, f"seed=42 not reproducible for {nom}"


def test_different_seeds_produce_different_layouts(apartment):
    prog = _prog(apartment)
    adjs = _adjs(apartment)
    W, H = _env(apartment)
    placed_0 = generate_layout(prog, adjs, W, H, seed=0)
    placed_1 = generate_layout(prog, adjs, W, H, seed=1)
    # At least one room should be in a different position
    diffs = []
    for nom in placed_0:
        r0 = placed_0[nom]
        r1 = placed_1[nom]
        if abs(r0.x - r1.x) > 0.01 or abs(r0.y - r1.y) > 0.01:
            diffs.append(nom)
    assert len(diffs) > 0, "seed=0 and seed=1 produced identical layouts"


def test_school_programme_no_overflow():
    path = os.path.join(os.path.dirname(__file__), "fixtures", "school_programme.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    prog = data["programme"]
    adjs = [tuple(a) for a in data["adjacencies"]]
    W, H = data["envelope"]["W"], data["envelope"]["H"]
    placed = generate_layout(prog, adjs, W, H, seed=0)
    for nom, rect in placed.items():
        assert rect.in_envelope(W, H), f"School: {nom} overflows"


def test_fallback_tight_envelope_doesnt_crash():
    """Generator should not raise even with a very small envelope."""
    prog = [
        {"nom": "A", "surface": 10, "couleur": "#aaa", "facade": False},
        {"nom": "B", "surface": 10, "couleur": "#bbb", "facade": False},
    ]
    adjs = [("A", "B")]
    # Tight envelope — generator will need fallback paths
    placed = generate_layout(prog, adjs, 8, 5, seed=0)
    assert len(placed) == 2
