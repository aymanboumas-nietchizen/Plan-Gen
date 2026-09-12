"""
core/geometry.py  –  Sprint 0 rewrite
======================================
Rooms and envelopes are now Shapely Polygons which support any shape
(L-shape, T-shape, irregular polygons).  The old Rect API is kept as a
backward-compatible factory that returns a Room object.

All distances and dimensions are in metres.
"""

from __future__ import annotations

import collections
import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

from shapely.geometry import Polygon, box, Point


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------

@dataclass
class Envelope:
    """Floor-plan boundary as a Shapely Polygon (any closed shape)."""
    polygon: Polygon

    @classmethod
    def from_rect(cls, W: float, H: float) -> "Envelope":
        """Rectangular envelope W x H, origin (0,0)."""
        return cls(box(0.0, 0.0, W, H))

    @classmethod
    def from_coords(cls, coords: list) -> "Envelope":
        """
        Arbitrary envelope from vertex list.
        E.g. L-shape: [[0,0],[12,0],[12,5],[8,5],[8,9],[0,9]]
        """
        poly = Polygon(coords)
        if not poly.is_valid:
            poly = poly.buffer(0)
        return cls(poly)

    @classmethod
    def from_dxf(cls, filepath: str) -> "Envelope":
        """Parse first closed LWPOLYLINE/POLYLINE from a DXF file."""
        try:
            import ezdxf
        except ImportError:
            raise ImportError("pip install ezdxf  to use from_dxf()")
        doc = ezdxf.readfile(filepath)
        for entity in doc.modelspace():
            if entity.dxftype() in ("LWPOLYLINE", "POLYLINE"):
                try:
                    pts = [(p[0], p[1]) for p in entity.get_points()]
                    if len(pts) >= 3:
                        return cls.from_coords(pts)
                except Exception:
                    continue
        raise ValueError(f"No usable closed polyline in {filepath}")

    @classmethod
    def from_json(cls, d: dict) -> "Envelope":
        """
        Parse from programme JSON dict.
            {"W":12,"H":9}                         -> rectangle
            {"coords":[[0,0],[12,0],[12,5],...]}   -> any polygon
            {"dxf":"./envelope.dxf"}               -> DXF import
        """
        if "coords" in d:
            return cls.from_coords(d["coords"])
        if "dxf" in d:
            return cls.from_dxf(d["dxf"])
        W = float(d.get("W") or d.get("width", 12.0))
        H = float(d.get("H") or d.get("height", 9.0))
        return cls.from_rect(W, H)

    @property
    def area(self) -> float:
        return self.polygon.area

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        return self.polygon.bounds

    @property
    def W(self) -> float:
        minx, _, maxx, _ = self.polygon.bounds
        return maxx - minx

    @property
    def H(self) -> float:
        _, miny, _, maxy = self.polygon.bounds
        return maxy - miny

    def to_dict(self) -> dict:
        coords = list(self.polygon.exterior.coords)
        return {"coords": [(round(x, 3), round(y, 3)) for x, y in coords]}


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------

@dataclass
class Room:
    """
    A room as a Shapely Polygon.

    Supported shapes:
        Room.from_rect(x, y, w, h, nom)          -> rectangle
        Room.from_l(x, y, ow, oh, cw, ch, nom)  -> L-shape
        Room.from_coords(coords, nom)             -> any polygon

    All spatial ops use Shapely so they work for any polygon shape.
    """
    polygon: Polygon
    nom: str
    color: str = "#cccccc"

    # --- Factories -----------------------------------------------------------

    @classmethod
    def from_rect(cls, x: float, y: float, w: float, h: float,
                  nom: str, color: str = "#cccccc") -> "Room":
        """Rectangular room at (x,y) with size w x h."""
        return cls(polygon=box(x, y, x + w, y + h), nom=nom, color=color)

    @classmethod
    def from_coords(cls, coords: list, nom: str,
                    color: str = "#cccccc") -> "Room":
        """Room from explicit vertex list (L-shape, irregular, etc.)."""
        poly = Polygon(coords)
        if not poly.is_valid:
            poly = poly.buffer(0)
        return cls(polygon=poly, nom=nom, color=color)

    @classmethod
    def from_l(cls, x: float, y: float,
               outer_w: float, outer_h: float,
               cutout_w: float, cutout_h: float,
               nom: str, color: str = "#cccccc") -> "Room":
        """
        L-shaped room: full rect (outer_w x outer_h) minus top-right corner
        (cutout_w x cutout_h).
        """
        coords = [
            (x,                      y),
            (x + outer_w,            y),
            (x + outer_w,            y + outer_h - cutout_h),
            (x + outer_w - cutout_w, y + outer_h - cutout_h),
            (x + outer_w - cutout_w, y + outer_h),
            (x,                      y + outer_h),
        ]
        return cls.from_coords(coords, nom, color)

    # --- Properties ----------------------------------------------------------

    @property
    def area(self) -> float:
        return self.polygon.area

    @property
    def cx(self) -> float:
        return self.polygon.centroid.x

    @property
    def cy(self) -> float:
        return self.polygon.centroid.y

    @property
    def ratio(self) -> float:
        """Elongation ratio from bounding box: max(w,h)/min(w,h)."""
        minx, miny, maxx, maxy = self.polygon.bounds
        bw, bh = maxx - minx, maxy - miny
        return (max(bw, bh) / min(bw, bh)) if min(bw, bh) > 0 else float("inf")

    @property
    def coords(self) -> List[Tuple[float, float]]:
        return list(self.polygon.exterior.coords)

    # Backward-compat bbox properties matching old Rect API
    @property
    def x(self) -> float:
        return self.polygon.bounds[0]

    @property
    def y(self) -> float:
        return self.polygon.bounds[1]

    @property
    def w(self) -> float:
        minx, _, maxx, _ = self.polygon.bounds
        return maxx - minx

    @property
    def h(self) -> float:
        _, miny, _, maxy = self.polygon.bounds
        return maxy - miny

    # --- Spatial relations ---------------------------------------------------

    def intersects_room(self, other: "Room", tol: float = 0.05) -> bool:
        """
        True if rooms overlap by more than tol metres.
        Buffer(-tol) ensures touching rooms are NOT flagged as overlapping.
        Works for any polygon shape.
        """
        a = self.polygon.buffer(-tol)
        b = other.polygon.buffer(-tol)
        if a.is_empty or b.is_empty:
            return False
        return bool(a.intersects(b))

    def touches_room(self, other: "Room", tol: float = 0.15) -> bool:
        """
        True if rooms share a wall (boundary within tol) but do NOT overlap.
        Works for any polygon shape — L-shaped, rectangular, etc.
        tol=0.15 m matches DTU adjacency interpretation.
        """
        if self.intersects_room(other, tol=0.01):
            return False
        return bool(self.polygon.boundary.distance(other.polygon.boundary) <= tol)

    # Backward-compat aliases
    def intersects(self, other: "Room", tol: float = 0.05) -> bool:
        return self.intersects_room(other, tol)

    def touches(self, other: "Room", tol: float = 0.15) -> bool:
        return self.touches_room(other, tol)

    def in_envelope(self, envelope, H: float = None) -> bool:
        """
        True if this room is entirely within the envelope.

        Accepts:
            room.in_envelope(envelope_obj)     -> Envelope (preferred)
            room.in_envelope(W, H=H)           -> backward-compat rectangle
        """
        if isinstance(envelope, Envelope):
            env_poly = envelope.polygon
        elif isinstance(envelope, (int, float)) and H is not None:
            env_poly = box(0.0, 0.0, float(envelope), float(H))
        else:
            raise TypeError("Pass Envelope, or (W: float, H=float)")
        return bool(env_poly.buffer(1e-6).covers(self.polygon))

    def on_facade(self, envelope, H: float = None, tol: float = 0.15) -> bool:
        """
        True if any edge of this room is within tol of the envelope boundary.
        Works for any envelope shape (L, T, rectangle, etc.).

        Accepts:
            room.on_facade(envelope_obj)       -> Envelope (preferred)
            room.on_facade(W, H=H)             -> backward-compat rectangle
        """
        if isinstance(envelope, Envelope):
            env_bnd = envelope.polygon.boundary
        elif isinstance(envelope, (int, float)) and H is not None:
            env_bnd = box(0.0, 0.0, float(envelope), float(H)).boundary
        else:
            raise TypeError("Pass Envelope, or (W: float, H=float)")
        return bool(self.polygon.boundary.distance(env_bnd) <= tol)

    # --- Serialisation ------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "nom":    self.nom,
            "area":   round(self.area, 2),
            "cx":     round(self.cx, 3),
            "cy":     round(self.cy, 3),
            "x":      round(self.x, 3),
            "y":      round(self.y, 3),
            "w":      round(self.w, 3),
            "h":      round(self.h, 3),
            "coords": [(round(c[0], 3), round(c[1], 3)) for c in self.coords],
            "color":  self.color,
        }


# ---------------------------------------------------------------------------
# Backward-compatible Rect factory
# ---------------------------------------------------------------------------

def Rect(x: float, y: float, w: float, h: float,
         nom: str, color: str = "#cccccc") -> Room:
    """
    Backward-compatible factory: returns a rectangular Room.
    All existing code that calls Rect(x, y, w, h, nom) continues to work.
    """
    return Room.from_rect(x, y, w, h, nom, color)


# ---------------------------------------------------------------------------
# Graph utilities (unchanged — operate only on room names)
# ---------------------------------------------------------------------------

def build_graph(rooms: list, adjacencies: list) -> Dict[str, List[str]]:
    """Build bidirectional adjacency map from programme + adjacency rules."""
    graph: Dict[str, List[str]] = {r["nom"]: [] for r in rooms}
    for a, b in adjacencies:
        if a not in graph or b not in graph:
            continue
        if b not in graph[a]:
            graph[a].append(b)
        if a not in graph[b]:
            graph[b].append(a)
    return graph


def bfs_order(graph: Dict[str, List[str]], start: str,
              all_rooms: list) -> List[str]:
    """BFS from start; unreachable rooms appended at end."""
    visited: List[str] = []
    queue = collections.deque([start])
    seen = {start}
    while queue:
        node = queue.popleft()
        visited.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    for nom in all_rooms:
        if nom not in seen:
            visited.append(nom)
    return visited


# ---------------------------------------------------------------------------
# Helper: L-shape dimensions from target area
# ---------------------------------------------------------------------------

def make_l_dims(area: float,
                aspect: List[float]) -> Tuple[float, float, float, float]:
    """
    Return (outer_w, outer_h, cutout_w, cutout_h) such that the L-shape area
    equals ``area``, with proportions given by ``aspect``.

    aspect = [outer_w_ratio, outer_h_ratio, cutout_w_ratio, cutout_h_ratio]
    """
    ow, oh, cw, ch = aspect
    net = ow * oh - cw * ch
    if net <= 0:
        raise ValueError(f"Invalid L aspect {aspect}: net area <= 0")
    s = math.sqrt(area / net)
    return s * ow, s * oh, s * cw, s * ch