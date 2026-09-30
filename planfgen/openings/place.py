"""L6 — putting the openings on the walls, and saying what could not be done.

Two rules govern everything here, and both are refusals rather than preferences.
A door goes only where the shared run can host one — a leaf plus its frame each
side, sized by the kind of room it serves (`door_module_for`: 0.83 m for a WC,
1.03 m for a bedroom) — which is the measurement ARCHITECTURE section 1 says v1
never made. A window goes only where `parcel.openable(edge)`
allows, which is not a matter of degree.

Anything that could not be placed comes back in `OpeningReport.errors`. A room
that needs daylight and has no wall to take it is not a low-scoring room; it is
a mistake, and it is named.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from planfgen.brief.regulation import RegulationProfile
from planfgen.fabric.axis import WallAxis, WallKind
from planfgen.fabric.plan import FabricPlan, Space
from planfgen.circulation.reachable import access_tree
from planfgen.openings.door import Door, Passage, free_slot
from planfgen.openings.window import Window, needs_daylight, required_glazing, size_windows
from planfgen.topology.relations import RelationType


@dataclass
class OpeningReport:
    """Everything placed, and everything that could not be."""

    doors: list[Door] = field(default_factory=list)
    windows: list[Window] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    passages: list[Passage] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def explain(self) -> str:
        head = f"{len(self.doors)} doors, {len(self.windows)} windows"
        if self.passages:
            head += f", {len(self.passages)} open passages"
        return head if self.ok else f"{head}; {len(self.errors)} unresolved: " + "; ".join(
            self.errors
        )


def _side_of(wall: WallAxis, space: Space) -> int:
    """+1 if the space lies on the wall's +y side (horizontal wall) or +x side
    (vertical wall), -1 otherwise — the convention `Door.clearance_box`, the DXF
    and the web drawing all read `swing_side` in.

    It used to be the wall's left normal, which is +y for a horizontal wall but
    -x for a vertical one (p0 is the lower end): every door on a vertical wall
    swung into the room it did not name. Found by the L7 layout (S31).
    """
    x0, y0 = wall.p0
    cx, cy = space.net_polygon.centroid.x, space.net_polygon.centroid.y
    if wall.is_horizontal:
        return 1 if cy >= y0 else -1
    return 1 if cx >= x0 else -1


def _swing_target(fabric: FabricPlan, a: str, b: str) -> str:
    """The space a door's leaf opens into: the room, never the corridor or hall
    it is entered from. Between two rooms, `b` as before."""
    if fabric.spaces[b].kind.is_circulation and not fabric.spaces[a].kind.is_circulation:
        return a
    return b


def place_doors(fabric: FabricPlan, topology, profile: RegulationProfile) -> OpeningReport:
    """An open passage wherever two circulation spaces meet, one door per
    CONNECTED relation, plus the front door.

    Passages come first and are not asked for by any relation: reachability
    already walks through every junction of two circulation spaces
    (`FabricPlan.door_capable`), so each one must be built open. A CONNECTED
    relation between two circulation spaces is one of those passages.

    A relation whose rooms share less than the opening needs gets no door and
    an error. So does one whose wall already carries an opening the new leaf
    would sweep into — two doors may share a wall only if their clearances do
    not meet.
    """
    report = OpeningReport()
    on_wall: dict[int, list] = {}
    joined: set[frozenset[str]] = set()

    noms = sorted(fabric.spaces)
    for i, a in enumerate(noms):
        for b in noms[i + 1:]:
            if fabric.is_passage(a, b) and fabric.door_capable(a, b):
                _place_passage(fabric, profile, report, on_wall, a, b)
                joined.add(frozenset((a, b)))

    for relation in topology.graph.of_kind(RelationType.CONNECTED):
        a, b = relation.pair
        if a not in fabric.spaces or b not in fabric.spaces:
            report.errors.append(f"{a}~{b}: the plan has no such room")
            continue
        if frozenset((a, b)) in joined:
            continue

        # The leaf opens into the room, never into the corridor or hall it is
        # entered from (`_swing_target`, S31 layout fix).
        if _hang(fabric, profile, report, on_wall, a, b,
                 swing_into=_swing_target(fabric, a, b)):
            joined.add(frozenset((a, b)))

    # Every room its door. Relations say which doors the architect wants;
    # reachability (L5) proves a legal way to every room over door-capable
    # walls, and a room no relation connects that way still has to be
    # entered: it gets its door on that way (`access_tree`), so the plan as
    # drawn is the plan the gate passed. (2026-09-30: 98 of 108 generated
    # plans had a room with no door at all.)
    _place_entry(fabric, profile, report, on_wall)
    missing = set(unentered(fabric, report))
    for room, parent in access_tree(fabric, joined).items():
        if room in missing and room in unentered(fabric, report):
            _hang(fabric, profile, report, on_wall, parent, room, swing_into=room)
    return report


def _hang(fabric, profile, report: OpeningReport, on_wall, a: str, b: str, swing_into: str) -> bool:
    """One door between `a` and `b`, or an error saying why not."""
    run = fabric.shared_wall_length(a, b)
    if not fabric.door_capable(a, b):
        what = "an open passage" if fabric.is_passage(a, b) else "a door"
        report.errors.append(
            f"{a}~{b}: {run:.2f} m of shared wall, under the "
            f"{fabric.opening_run(a, b):.2f} m {what} needs"
        )
        return False

    wall = fabric.graph.wall_between(
        fabric.spaces[a].axis_polygon, fabric.spaces[b].axis_polygon
    )
    if wall is None:
        report.errors.append(f"{a}~{b}: {run:.2f} m shared but no single wall to host a door")
        return False

    kind = fabric.door_kind(a, b)
    leaf = profile.door_leaf_for(kind)
    taken = on_wall.setdefault(id(wall), [])
    t = free_slot(wall, taken, leaf, profile.door_frame_for(kind),
                  _clear_run(fabric, a, b, wall))
    if t is None:
        report.errors.append(
            f"{a}~{b}: no room left on that wall clear of the doors already on it"
        )
        return False

    door = Door(
        wall=wall,
        t=t,
        leaf=leaf,
        swing_into=swing_into,
        hinge="low",
        swing_side=_side_of(wall, fabric.spaces[swing_into]),
    )
    taken.append(door)
    report.doors.append(door)
    return True


def _clear_run(fabric, a: str, b: str, wall: WallAxis) -> tuple[float, float]:
    """The stretch of `wall`, in metres from its `p0`, that faces both rooms'
    clear floor: a door there stands clear of the walls meeting it, instead of
    starting at the axis crossing inside their thickness."""
    axis = 0 if wall.is_horizontal else 1
    origin = min(wall.p0[axis], wall.p1[axis])
    ba, bb = fabric.spaces[a].net_polygon.bounds, fabric.spaces[b].net_polygon.bounds
    low = max(ba[axis], bb[axis], origin) - origin
    high = min(ba[axis + 2], bb[axis + 2], origin + wall.length) - origin
    return low, high


def door_graph(fabric: FabricPlan, report: OpeningReport) -> dict[str, set[str]]:
    """Which spaces open onto which, over the openings actually placed."""
    owners: dict[int, list[str]] = {}
    for nom, space in fabric.spaces.items():
        for wall in space.bounding:
            owners.setdefault(id(wall), []).append(nom)
    graph: dict[str, set[str]] = {nom: set() for nom in fabric.spaces}
    for opening in (*report.doors, *report.passages):
        pair = owners.get(id(opening.wall), [])
        if len(pair) == 2:
            a, b = pair
            graph[a].add(b)
            graph[b].add(a)
    return graph


def unentered(fabric: FabricPlan, report: OpeningReport) -> list[str]:
    """Spaces the drawn doors do not reach from the front door, walking only
    through circulation (and `PASS_THROUGH`): what L5 checks, asked of what L6
    built. Empty for a plan whose every room can actually be entered."""
    from planfgen.circulation.reachable import PASS_THROUGH, entry_space

    try:
        entry = entry_space(fabric).nom
    except ValueError:
        return sorted(fabric.spaces)
    graph = door_graph(fabric, report)
    kind = {nom: space.kind for nom, space in fabric.spaces.items()}
    seen, queue = {entry}, [entry]
    while queue:
        current = queue.pop()
        passable = current == entry or kind[current].is_circulation
        for other in graph[current]:
            if other in seen:
                continue
            if passable or (kind[other], kind[current]) in PASS_THROUGH:
                seen.add(other)
                queue.append(other)
    return sorted(set(fabric.spaces) - seen)


def _place_passage(fabric, profile, report: OpeningReport, on_wall, a: str, b: str) -> None:
    """Open the wall between two circulation spaces over the corridor's clear width.

    Centred on where their net outlines overlap along the wall — for a
    T-junction, exactly the end of the band — and never wider than that
    overlap nor than `corridor_clear`.
    """
    wall = fabric.graph.wall_between(
        fabric.spaces[a].axis_polygon, fabric.spaces[b].axis_polygon
    )
    if wall is None:
        report.errors.append(f"{a}~{b}: they meet but share no single wall to open")
        return
    axis = 0 if wall.is_horizontal else 1
    origin = min(wall.p0[axis], wall.p1[axis])
    ba, bb = fabric.spaces[a].net_polygon.bounds, fabric.spaces[b].net_polygon.bounds
    low = max(ba[axis], bb[axis], origin) - origin
    high = min(ba[axis + 2], bb[axis + 2], origin + wall.length) - origin
    if high - low <= 1e-9:
        low, high = 0.0, wall.length           # no net overlap to read: the wall itself
    width = min(profile.corridor_clear, high - low)
    passage = Passage(wall, ((low + high) / 2) / wall.length, width, (a, b))
    taken = on_wall.setdefault(id(wall), [])
    if any(passage.clashes_with(other) for other in taken):
        report.errors.append(f"{a}~{b}: the passage would cut through a door")
        return
    taken.append(passage)
    report.passages.append(passage)


def _place_entry(fabric, profile, report: OpeningReport, on_wall) -> None:
    """The front door, on the parcel's entry edge."""
    from planfgen.circulation.reachable import entry_space

    try:
        entry = entry_space(fabric)
    except ValueError as exc:
        report.errors.append(f"entry door: {exc}")
        return

    candidates = [
        wall
        for wall in fabric.walls_on_edge(entry, fabric.parcel.entry_edge)
        if wall.kind is WallKind.FACADE and wall.length >= profile.entry_module
    ]
    if not candidates:
        report.errors.append(
            f"entry door: {entry.nom} has no facade run on edge "
            f"{fabric.parcel.entry_edge} long enough for a "
            f"{profile.entry_leaf:.2f} m leaf"
        )
        return

    wall = max(candidates, key=lambda w: w.length)
    taken = on_wall.setdefault(id(wall), [])
    axis = 0 if wall.is_horizontal else 1
    origin = min(wall.p0[axis], wall.p1[axis])
    bounds = entry.net_polygon.bounds
    run = (max(bounds[axis] - origin, 0.0), min(bounds[axis + 2] - origin, wall.length))
    t = free_slot(wall, taken, profile.entry_leaf, profile.door_jamb, run)
    if t is None:
        report.errors.append(f"entry door: no clear run on {entry.nom}'s street facade")
        return

    door = Door(
        wall=wall,
        t=t,
        leaf=profile.entry_leaf,
        swing_into=entry.nom,
        hinge="low",
        swing_side=_side_of(wall, entry),
    )
    taken.append(door)
    report.doors.append(door)


def openable_walls(fabric: FabricPlan, space: Space) -> list[WallAxis]:
    """The space's exterior walls that sit on an edge a window may pierce."""
    parcel = fabric.parcel
    found: list[WallAxis] = []
    for edge in range(len(parcel.outline.exterior.coords) - 1):
        if not parcel.openable(edge):
            continue
        for wall in fabric.walls_on_edge(space, edge):
            if not any(wall is seen for seen in found):
                found.append(wall)
    return found


def place_windows(
    fabric: FabricPlan, profile: RegulationProfile, programme=None
) -> OpeningReport:
    """Windows on legal edges only; a blind daylight room is an error.

    Every room of a `DAYLIGHT_KINDS` kind is lit: decret ART. 7 is a law, and
    since 2026-09-29 a gate (`DAYLIGHT_GATE`), so no line of brief can waive it.
    `programme` is optional; where it is to hand its `daylight` flag can ask
    for MORE light — a window in a room the law does not require one in.
    """
    report = OpeningReport()

    for nom, space in fabric.spaces.items():
        wanted = needs_daylight(space)
        if programme is not None:
            wanted = wanted or programme.by_nom(nom).daylight
        if not wanted:
            continue

        walls = openable_walls(fabric, space)
        if not walls:
            report.errors.append(
                f"{nom}: needs daylight and has no openable exterior wall"
            )
            continue

        placed = size_windows(space, walls, profile)
        report.windows.extend(placed)
        got = sum(window.glazing for window in placed)
        needed = required_glazing(space, profile)
        if got + 1e-9 < needed:
            report.errors.append(
                f"{nom}: {got:.2f} m2 of glazing against {needed:.2f} m2 required"
            )
    return report


def place_openings(
    fabric: FabricPlan, topology, profile: RegulationProfile, programme=None
) -> OpeningReport:
    """Doors and windows together, with one report over both."""
    doors = place_doors(fabric, topology, profile)
    windows = place_windows(fabric, profile, programme)
    return OpeningReport(
        doors=doors.doors,
        windows=windows.windows,
        errors=doors.errors + windows.errors,
        passages=doors.passages,
    )
