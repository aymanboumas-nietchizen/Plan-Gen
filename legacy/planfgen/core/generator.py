"""
core/generator.py  –  Sprint 0 update
=======================================
Graph-guided BFS layout generator, now polygon-aware.

The envelope is a Shapely Polygon (any shape — rectangle, L, T, etc.).
Rooms are placed using Room.from_rect() by default, with L-shaped and
custom polygon rooms supported via the "shape"/"coords" programme keys.

Algorithm:
  1. Build adjacency graph
  2. Find hub room (highest degree × area)
  3. BFS traversal order from hub
  4. Place hub room at a seed-dependent corner of the envelope bounding box
  5. For each remaining room in BFS order:
       a. Compute target dimensions from area (varied by seed)
       b. Generate 8 directional candidates around placed neighbours
       c. Filter: room.in_envelope(envelope) AND no intersects_room() clash
       d. Shuffle by seed; pick first valid
       e. Fallback: raster grid over envelope bounding box
  6. Retry with smaller area if overlap persists
  7. Return {nom: Room}

Rule-agnostic — scoring and DTU validation happen downstream.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

from shapely import MultiPoint, Point
from shapely.ops import voronoi_diagram

from planfgen.core.geometry import (
    Room, Envelope, Rect, build_graph, bfs_order, make_l_dims
)


_ASPECT_CANDIDATES = [0.80, 1.00, 1.25, 1.50, 0.67]
_MAX_RATIO         = 2.5
_GRID_STEP         = 0.30
_AREA_FACTORS      = [1.0, 0.92]


def _compute_dimensions(area: float, aspect: float) -> Tuple[float, float]:
    """(w, h) from target area and aspect ratio w/h, clamped to _MAX_RATIO."""
    w = math.sqrt(area * aspect)
    h = area / w if w > 0 else math.sqrt(area)
    if w / h > _MAX_RATIO:
        w = h * _MAX_RATIO
    if h / w > _MAX_RATIO:
        h = w * _MAX_RATIO
    return round(w, 3), round(h, 3)


def _make_room_for_programme(entry: dict, x: float, y: float,
                              rw: float, rh: float) -> Room:
    """
    Create a Room from a programme entry at position (x, y) with size rw x rh.

    Supports four room shapes via optional programme keys:
        (none)           -> rectangle (default)
        "shape": "L"     -> L-shaped, with "aspect": [ow, oh, cw, ch]
        "coords": [...]  -> explicit polygon vertices (placed relatively to x,y)
    """
    nom   = entry["nom"]
    color = entry.get("couleur", "#cccccc")
    shape = entry.get("shape", "rect").lower()

    if shape == "l":
        aspect_ratios = entry.get("aspect", [1.6, 1.0, 0.6, 0.4])
        area = rw * rh  # use the same area budget
        ow, oh, cw, ch = make_l_dims(area, aspect_ratios)
        return Room.from_l(x, y, ow, oh, cw, ch, nom, color)

    if "coords" in entry:
        # Relative coords — shift to placement position
        base_coords = entry["coords"]
        shifted = [(x + cx, y + cy) for cx, cy in base_coords]
        return Room.from_coords(shifted, nom, color)

    # Default: rectangle
    return Room.from_rect(x, y, rw, rh, nom, color)


def _candidate_positions(anchor: Room, rw: float, rh: float) -> List[Tuple[float, float]]:
    """8 candidate (x,y) positions around anchor room's bounding box."""
    ax, ay, aw, ah = anchor.x, anchor.y, anchor.w, anchor.h
    return [
        (ax + aw,       ay),
        (ax + aw,       ay + ah - rh),
        (ax - rw,       ay),
        (ax - rw,       ay + ah - rh),
        (ax,            ay + ah),
        (ax + aw - rw,  ay + ah),
        (ax,            ay - rh),
        (ax + aw - rw,  ay - rh),
    ]


def _envelope_candidates(rw: float, rh: float,
                         envelope: Envelope) -> List[Tuple[float, float]]:
    """
    Candidate positions at bounding-box corners/edges of the envelope.
    Useful for polygon envelopes where corners are valid start positions.
    """
    minx, miny, maxx, maxy = envelope.bounds
    W = maxx - minx
    H = maxy - miny
    return [
        (minx,               miny),
        (maxx - rw,          miny),
        (minx,               maxy - rh),
        (maxx - rw,          maxy - rh),
        (minx + (W - rw)/2,  miny),
        (minx + (W - rw)/2,  maxy - rh),
        (minx,               miny + (H - rh)/2),
        (maxx - rw,          miny + (H - rh)/2),
    ]


def _try_place_all(
    programme: list,
    adjacencies: list,
    envelope: Envelope,
    rng: random.Random,
    area_factor: float,
) -> Tuple[Dict[str, Room], bool]:
    """
    Attempt to place all rooms. Returns (placed_dict, success).
    success=True when every room is placed without overlap.
    """
    local_rng  = random.Random(rng.random())
    graph      = build_graph(programme, adjacencies)

    def hub_key(room):
        return len(graph.get(room["nom"], [])) * room["surface"]

    hub_nom = sorted(programme, key=hub_key, reverse=True)[0]["nom"]
    all_noms  = [r["nom"] for r in programme]
    order     = bfs_order(graph, hub_nom, all_noms)
    room_by_nom = {r["nom"]: r for r in programme}

    # ── Place hub room at a seed-dependent corner of the envelope bbox ──────
    placed: Dict[str, Room] = {}
    hub_entry = room_by_nom[hub_nom]
    hub_area  = hub_entry["surface"] * area_factor
    aspects   = _ASPECT_CANDIDATES[:]
    local_rng.shuffle(aspects)
    hub_w, hub_h = _compute_dimensions(hub_area, aspects[0])

    minx, miny, maxx, maxy = envelope.bounds
    corners = [
        (minx,           miny),
        (maxx - hub_w,   miny),
        (minx,           maxy - hub_h),
        (maxx - hub_w,   maxy - hub_h),
    ]
    local_rng.shuffle(corners)

    for hx, hy in corners:
        candidate_hub = _make_room_for_programme(hub_entry, hx, hy, hub_w, hub_h)
        if candidate_hub.in_envelope(envelope):
            placed[hub_nom] = candidate_hub
            break
    else:
        # Fallback: place hub at envelope centroid
        cx, cy = envelope.polygon.centroid.x - hub_w / 2, envelope.polygon.centroid.y - hub_h / 2
        placed[hub_nom] = _make_room_for_programme(hub_entry, cx, cy, hub_w, hub_h)

    overlap_occurred = False

    # ── Place remaining rooms in BFS order ───────────────────────────────────
    for nom in order:
        if nom in placed:
            continue

        entry  = room_by_nom[nom]
        area   = entry["surface"] * area_factor
        aspects = _ASPECT_CANDIDATES[:]
        local_rng.shuffle(aspects)

        best_room: Optional[Room] = None

        # Phase 1: directional candidates around placed neighbours
        for aspect in aspects:
            rw, rh = _compute_dimensions(area, aspect)

            neighbours = graph.get(nom, [])
            anchors = [placed[n] for n in neighbours if n in placed] or list(placed.values())

            candidates: List[Tuple[float, float]] = []
            for anchor in anchors:
                candidates.extend(_candidate_positions(anchor, rw, rh))
            candidates.extend(_envelope_candidates(rw, rh, envelope))
            local_rng.shuffle(candidates)

            for cx, cy in candidates:
                candidate = _make_room_for_programme(entry, cx, cy, rw, rh)
                if not candidate.in_envelope(envelope):
                    continue
                if any(candidate.intersects_room(p) for p in placed.values()):
                    continue
                best_room = candidate
                break

            if best_room is not None:
                break

        # Phase 2: raster grid scan inside envelope bounding box
        if best_room is None:
            minx, miny, maxx, maxy = envelope.bounds
            W_bb = maxx - minx
            H_bb = maxy - miny
            found = False
            for fallback_aspect in aspects:
                rw, rh = _compute_dimensions(area, fallback_aspect)
                ys = [round(miny + j * _GRID_STEP, 3)
                      for j in range(int(H_bb / _GRID_STEP) + 1)]
                xs = [round(minx + i * _GRID_STEP, 3)
                      for i in range(int(W_bb / _GRID_STEP) + 1)]
                local_rng.shuffle(ys)
                for fy in ys:
                    for fx in xs:
                        candidate = _make_room_for_programme(entry, fx, fy, rw, rh)
                        if not candidate.in_envelope(envelope):
                            continue
                        if any(candidate.intersects_room(p) for p in placed.values()):
                            continue
                        best_room = candidate
                        found = True
                        break
                    if found:
                        break
                if found:
                    break

        # Last resort: place at envelope centroid (overlap accepted)
        if best_room is None:
            overlap_occurred = True
            rw, rh = _compute_dimensions(area, 1.0)
            cx = envelope.polygon.centroid.x - rw / 2
            cy = envelope.polygon.centroid.y - rh / 2
            best_room = _make_room_for_programme(entry, cx, cy, rw, rh)

        placed[nom] = best_room

    return placed, not overlap_occurred


# ---------------------------------------------------------------------------
# Voronoi space-filling post-processing
# ---------------------------------------------------------------------------

def _voronoi_fill(
    placed: Dict[str, Room],
    envelope: Envelope,
) -> Dict[str, Room]:
    """
    Post-process BFS placement: replace rectangular rooms with Voronoi cells
    clipped to the envelope polygon.  This eliminates all gaps — every square
    metre of the envelope is assigned to a room.

    All rooms (including corridors) participate in the Voronoi partition.
    The corridor naturally gets a cell shaped by its position between other
    rooms (since BFS places it centrally due to high connectivity).
    """
    if len(placed) < 2:
        return placed  # Voronoi needs >= 2 points

    # 1. Build Voronoi from all room centroids
    room_list = list(placed.items())
    points = MultiPoint([(r.cx, r.cy) for _, r in room_list])
    try:
        regions = voronoi_diagram(points)
    except (ValueError, Exception):
        # Voronoi can fail with collinear or degenerate point sets
        return placed

    # 2. Assign each Voronoi cell to the room whose centroid it contains
    env_poly = envelope.polygon
    if not env_poly.is_valid:
        env_poly = env_poly.buffer(0)
    new_placed: Dict[str, Room] = {}
    for cell in regions.geoms:
        safe_cell = cell if cell.is_valid else cell.buffer(0)
        try:
            clipped = safe_cell.intersection(env_poly)
        except Exception:
            continue
        if clipped.is_empty or clipped.area < 0.01:
            continue
        # MultiPolygon (non-convex envelope) → take largest piece
        if clipped.geom_type == "MultiPolygon":
            clipped = max(clipped.geoms, key=lambda g: g.area)
        if clipped.geom_type != "Polygon":
            continue
        if not clipped.is_valid:
            clipped = clipped.buffer(0)
            if clipped.geom_type != "Polygon":
                continue
        for nom, room in room_list:
            if nom not in new_placed and clipped.contains(Point(room.cx, room.cy)):
                new_placed[nom] = Room.from_coords(
                    list(clipped.exterior.coords), nom, room.color
                )
                break

    # 3. Fallback: unassigned rooms keep original placement
    for nom in placed:
        if nom not in new_placed:
            new_placed[nom] = placed[nom]

    return new_placed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_layout(
    programme: list,
    adjacencies: list,
    envelope_or_W,
    H: float = None,
    seed: int = 0,
    W: float = None,
) -> Dict[str, Room]:
    """
    Generate a single floor plan layout using graph-guided BFS placement.

    Parameters
    ----------
    programme         : list of room dicts with ``nom``, ``surface``, ``couleur``
    adjacencies       : list of (str, str) tuples — desired spatial adjacencies
    envelope_or_W     : Envelope object (preferred) OR envelope width W (float,
                        backward compat when H is also provided)
    H                 : envelope height in metres (only used when envelope_or_W
                        is a float for backward compatibility)
    seed              : integer seed for reproducible randomness

    Returns
    -------
    dict  {room_nom: Room}
    """
    # ── Resolve envelope ────────────────────────────────────────────────────
    if isinstance(envelope_or_W, Envelope):
        envelope = envelope_or_W
    elif isinstance(envelope_or_W, (int, float)) and H is not None:
        envelope = Envelope.from_rect(float(envelope_or_W), float(H))
    elif W is not None and H is not None:
        envelope = Envelope.from_rect(float(W), float(H))
    else:
        raise TypeError("Pass an Envelope object or (W: float, H: float)")

    rng = random.Random(seed)

    for factor in _AREA_FACTORS:
        placed, success = _try_place_all(programme, adjacencies, envelope, rng, factor)
        if success:
            return _voronoi_fill(placed, envelope)

    return _voronoi_fill(placed, envelope)  # best-effort after all factors