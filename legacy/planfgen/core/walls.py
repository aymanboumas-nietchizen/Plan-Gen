"""
core/walls.py  –  Sprint 6
============================
Wall, Door, and Entrance system for PLANFGEN.

After rooms are placed (via generator), build_wall_system() derives:
  - 4 exterior walls (along the envelope boundary)
  - Interior walls between every pair of touching rooms
  - One interior door per shared wall (at the midpoint of the shared segment)
  - One entrance door on the most-connected facade room

All geometry uses Shapely so it works for any polygon room or envelope.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import  Dict, List, Optional, Tuple

from shapely.geometry import LineString, Point, MultiLineString, GeometryCollection
from shapely.ops import shared_paths

from planfgen.core.geometry import Room, Envelope


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Wall:
    """A single wall segment (line from (x0,y0) to (x1,y1))."""
    x0: float
    y0: float
    x1: float
    y1: float
    thickness: float          # metres: 0.30 exterior, 0.15 interior
    wall_type: str            # "exterior" | "interior"
    room_a: str               # nom of room on side A
    room_b: str = ""          # nom of room on side B ("" for exterior)

    @property
    def length(self) -> float:
        return ((self.x1 - self.x0)**2 + (self.y1 - self.y0)**2) ** 0.5

    @property
    def midpoint(self) -> Tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    def to_dict(self) -> dict:
        return {
            "type":      self.wall_type,
            "x0":        round(self.x0, 3),
            "y0":        round(self.y0, 3),
            "x1":        round(self.x1, 3),
            "y1":        round(self.y1, 3),
            "thickness": self.thickness,
            "room_a":    self.room_a,
            "room_b":    self.room_b,
        }


@dataclass
class Door:
    """A door opening in a wall."""
    wall: Wall
    cx: float              # centre of opening
    cy: float
    width: float           # clear opening (m)
    door_type: str         # "interior" | "entrance"

    def to_dict(self) -> dict:
        return {
            "type":   self.door_type,
            "cx":     round(self.cx, 3),
            "cy":     round(self.cy, 3),
            "width":  round(self.width, 3),
            "room_a": self.wall.room_a,
            "room_b": self.wall.room_b,
        }


@dataclass
class Window:
    """A window opening in an exterior wall."""
    wall: Wall
    cx: float              # centre of opening
    cy: float
    width: float           # clear opening (m), default 1.20

    def to_dict(self) -> dict:
        return {
            "cx":     round(self.cx, 3),
            "cy":     round(self.cy, 3),
            "width":  round(self.width, 3),
            "room":   self.wall.room_a,
        }


@dataclass
class WallSystem:
    """Complete wall + door system for a placed layout."""
    walls:    List[Wall]
    doors:    List[Door]
    entrance: Optional[Door] = None
    windows:  List[Window] = field(default_factory=list)

    def door_graph(self) -> Dict[str, List[str]]:
        """
        Returns {room_nom: [reachable_room_noms]} connected via interior doors.
        Used by access rules to check all rooms are reachable from entrance.
        """
        graph: Dict[str, List[str]] = {}
        for door in self.doors:
            a, b = door.wall.room_a, door.wall.room_b
            graph.setdefault(a, [])
            graph.setdefault(b, [])
            if b and b not in graph[a]:
                graph[a].append(b)
            if a and a not in graph.get(b, []):
                graph.setdefault(b, []).append(a)
        return graph

    def reachable_from(self, start_nom: str) -> List[str]:
        """BFS over door_graph from start room. Returns list of reachable noms."""
        graph   = self.door_graph()
        visited = []
        queue   = collections.deque([start_nom])
        seen    = {start_nom}
        while queue:
            node = queue.popleft()
            visited.append(node)
            for nb in graph.get(node, []):
                if nb and nb not in seen:
                    seen.add(nb)
                    queue.append(nb)
        return visited

    def to_dict(self) -> dict:
        return {
            "walls": [w.to_dict() for w in self.walls],
            "doors": [d.to_dict() for d in self.doors],
            "entrance": self.entrance.to_dict() if self.entrance else None,
            "windows": [w.to_dict() for w in self.windows],
        }


# ---------------------------------------------------------------------------
# Shared-edge detection
# ---------------------------------------------------------------------------

def _shared_edge(room_a: Room, room_b: Room, tol: float = 0.15):
    """
    Return a LineString of the shared boundary between room_a and room_b,
    or None if they don't share an edge within tol.

    Works for any polygon shape via Shapely shared_paths().
    """
    # Expand room_a slightly so touching boundaries actually intersect
    a_buf = room_a.polygon.buffer(tol / 2)
    b_bnd = room_b.polygon.boundary
    intersection = a_buf.boundary.intersection(b_bnd)

    if intersection.is_empty:
        return None

    # Extract the longest linear segment
    if isinstance(intersection, LineString) and intersection.length > 0.01:
        return intersection
    if hasattr(intersection, "geoms"):
        lines = [g for g in intersection.geoms if isinstance(g, LineString) and g.length > 0.01]
        if lines:
            return max(lines, key=lambda l: l.length)
    return None


# ---------------------------------------------------------------------------
# Door width rules
# ---------------------------------------------------------------------------

_SMALL_ROOM_TYPES = {"wc", "sdb", "bain", "toilet"}

def _door_width_for(room_nom: str) -> float:
    """Standard clear door width in metres based on room type."""
    nom_lower = room_nom.lower()
    if any(t in nom_lower for t in _SMALL_ROOM_TYPES):
        return 0.80   # WC, SDB
    return 0.90       # standard rooms


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_wall_system(
    placed: Dict[str, Room],
    adjacencies: list,
    envelope: Envelope,
    programme: list = None,
    ext_thickness: float = 0.30,
    int_thickness: float = 0.15,
) -> WallSystem:
    """
    Build the complete wall, door, and entrance system for a placed layout.

    Parameters
    ----------
    placed        : {nom: Room} from generate_layout()
    adjacencies   : list of (str, str) desired adjacency pairs
    envelope      : Envelope polygon
    programme     : list of room dicts (used to find facade rooms for entrance)
    ext_thickness : exterior wall thickness in metres (default 0.30)
    int_thickness : interior wall thickness in metres (default 0.15)

    Returns
    -------
    WallSystem with walls, doors, and entrance
    """
    if programme is None:
        programme = []

    walls: List[Wall] = []
    doors: List[Door] = []

    # ── 1. Exterior walls (envelope perimeter segments) ────────────────────
    env_coords = list(envelope.polygon.exterior.coords)
    for i in range(len(env_coords) - 1):
        x0, y0 = env_coords[i]
        x1, y1 = env_coords[i + 1]
        seg_len = ((x1 - x0)**2 + (y1 - y0)**2) ** 0.5
        if seg_len < 0.01:
            continue
        # Find room closest to this wall segment (room_a for label)
        seg_mid = Point((x0 + x1) / 2, (y0 + y1) / 2)
        nearest_nom = ""
        min_dist = float("inf")
        for nom, room in placed.items():
            d = room.polygon.boundary.distance(seg_mid)
            if d < min_dist:
                min_dist = d
                nearest_nom = nom
        walls.append(Wall(
            x0=round(x0, 3), y0=round(y0, 3),
            x1=round(x1, 3), y1=round(y1, 3),
            thickness=ext_thickness,
            wall_type="exterior",
            room_a=nearest_nom,
            room_b="",
        ))

    # ── 2. Interior walls and doors for touching room pairs ────────────────
    processed_pairs = set()
    room_noms = list(placed.keys())

    for i, nom_a in enumerate(room_noms):
        for nom_b in room_noms[i + 1:]:
            pair = tuple(sorted([nom_a, nom_b]))
            if pair in processed_pairs:
                continue
            room_a = placed[nom_a]
            room_b = placed[nom_b]
            if not room_a.touches_room(room_b, tol=int_thickness + 0.05):
                continue
            processed_pairs.add(pair)

            edge = _shared_edge(room_a, room_b, tol=int_thickness + 0.05)
            if edge is None:
                # Approximate: use line between centroids clipped
                cx_a, cy_a = room_a.cx, room_a.cy
                cx_b, cy_b = room_b.cx, room_b.cy
                mx, my = (cx_a + cx_b)/2, (cy_a + cy_b)/2
                walls.append(Wall(
                    x0=round(cx_a, 3), y0=round(cy_a, 3),
                    x1=round(cx_b, 3), y1=round(cy_b, 3),
                    thickness=int_thickness,
                    wall_type="interior",
                    room_a=nom_a,
                    room_b=nom_b,
                ))
                door_w = min(_door_width_for(nom_a), _door_width_for(nom_b))
                wall_obj = walls[-1]
                doors.append(Door(
                    wall=wall_obj,
                    cx=round(mx, 3), cy=round(my, 3),
                    width=door_w,
                    door_type="interior",
                ))
            else:
                coords = list(edge.coords)
                x0_e, y0_e = coords[0]
                x1_e, y1_e = coords[-1]
                wall_obj = Wall(
                    x0=round(x0_e, 3), y0=round(y0_e, 3),
                    x1=round(x1_e, 3), y1=round(y1_e, 3),
                    thickness=int_thickness,
                    wall_type="interior",
                    room_a=nom_a,
                    room_b=nom_b,
                )
                walls.append(wall_obj)
                mx, my = wall_obj.midpoint
                door_w = min(_door_width_for(nom_a), _door_width_for(nom_b))
                doors.append(Door(
                    wall=wall_obj,
                    cx=round(mx, 3), cy=round(my, 3),
                    width=round(door_w, 3),
                    door_type="interior",
                ))

    # ── 3. Entrance door on most-connected facade room ─────────────────────
    facade_noms = {r["nom"] for r in programme if r.get("facade", False)}

    # Count interior door connections per room
    door_count: Dict[str, int] = {nom: 0 for nom in placed}
    for door in doors:
        a, b = door.wall.room_a, door.wall.room_b
        door_count[a] = door_count.get(a, 0) + 1
        if b:
            door_count[b] = door_count.get(b, 0) + 1

    # Candidate facade rooms: must actually be on the envelope boundary
    tol_facade = ext_thickness + 0.05
    candidates = [
        nom for nom in facade_noms
        if nom in placed and placed[nom].on_facade(envelope, tol=tol_facade)
    ]
    if not candidates:
        candidates = [nom for nom in placed if placed[nom].on_facade(envelope, tol=tol_facade)] or list(placed.keys())

    entrance_room_nom = max(candidates, key=lambda n: door_count.get(n, 0))
    entrance_room = placed[entrance_room_nom]

    # Place entrance at the midpoint of the room's boundary closest to the
    # envelope boundary (works for any polygon shape)
    env_bnd = envelope.polygon.boundary
    room_bnd = entrance_room.polygon.boundary
    nearest_pt_on_env = env_bnd.interpolate(env_bnd.project(room_bnd.centroid))
    nearest_pt_on_room = room_bnd.interpolate(room_bnd.project(nearest_pt_on_env))

    # Place entrance on the exterior wall closest to this room
    entrance_cx = (nearest_pt_on_env.x + nearest_pt_on_room.x) / 2
    entrance_cy = (nearest_pt_on_env.y + nearest_pt_on_room.y) / 2

    # Find the exterior wall segment this entrance belongs to
    entrance_wall = min(
        (w for w in walls if w.wall_type == "exterior" and w.room_a == entrance_room_nom),
        key=lambda w: ((w.midpoint[0]-entrance_cx)**2 + (w.midpoint[1]-entrance_cy)**2)**0.5,
        default=next((w for w in walls if w.wall_type == "exterior"), walls[0] if walls else None),
    )

    if entrance_wall is not None:
        entrance = Door(
            wall=entrance_wall,
            cx=round(entrance_cx, 3),
            cy=round(entrance_cy, 3),
            width=1.00,
            door_type="entrance",
        )
        doors.append(entrance)
    else:
        entrance = None

    # ── 4. Windows on exterior walls for facade rooms ──────────────────────
    windows: List[Window] = []
    facade_rooms_with_windows = {r["nom"] for r in programme if r.get("facade", False)}

    for nom in facade_rooms_with_windows:
        if nom not in placed:
            continue
        # Find the exterior wall closest to this room
        ext_walls_for_room = [
            w for w in walls
            if w.wall_type == "exterior" and w.room_a == nom
        ]
        if not ext_walls_for_room:
            # Fallback: find nearest exterior wall
            ext_walls_for_room = [w for w in walls if w.wall_type == "exterior"]
        if not ext_walls_for_room:
            continue
        # Pick the longest exterior wall for this room
        best_wall = max(ext_walls_for_room, key=lambda w: w.length)
        # Skip if too short or if it's the entrance wall
        if best_wall.length < 0.80:
            continue
        win_width = min(1.20, best_wall.length - 0.60)
        if win_width < 0.40:
            continue
        mx, my = best_wall.midpoint
        windows.append(Window(
            wall=best_wall,
            cx=round(mx, 3), cy=round(my, 3),
            width=round(win_width, 3),
        ))

    return WallSystem(walls=walls, doors=doors, entrance=entrance, windows=windows)